import logging
import re
from decimal import Decimal, InvalidOperation
from celery import shared_task
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from .models import TrackedProduct, PriceHistory

logger = logging.getLogger(__name__)
User = get_user_model()

def parse_price_from_text(text):
    """Sanitizes raw text metrics and isolates absolute numeric floating values."""
    if not text:
        return None
    
    # Text mein se spaces, commas, aur currency symbols saaf karein
    cleaned_text = text.replace(',', '').strip()
    
    # Saare numbers extract karein (including decimals)
    numbers = re.findall(r'\d+(?:\.\d+)?', cleaned_text)
    
    valid_prices = []
    for num in numbers:
        try:
            val = float(num)
            # Hum 10 Rs se chhoti values ko ignore karenge (kyunki PKR mein 10 Rs se sasta aur khaskar earbuds nahi hote)
            # Is se 0.56, 0.44 ya discount percentages filter out ho jayengi.
            if val > 10.0:
                valid_prices.append(val)
        except ValueError:
            continue
            
    # Agar humein koi valid price mili hai, to pehli valid price return karein
    if valid_prices:
        return valid_prices[0]
        
    # Fallback: Agar saari hi choti values hain to majbooran pehli value return karein
    if numbers:
        try:
            return float(numbers[0])
        except ValueError:
            pass
            
    return None

def execute_playwright_scrape(url):
    """Launches isolated headless browser core to acquire fully rendered DOM states."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)  # Playwright wait
            content = page.content()
            return content
        except Exception as e:
            print(f"Playwright pipeline aborted execution safely over remote source target: {str(e)}")
            return None
        finally:
            browser.close()

@shared_task(name="trackers.tasks.scrape_single_product")
def scrape_single_product(product_id):
    """Processes explicit product rows, extracts metrics, models price arrays and fires live sockets."""
    try:
        product = TrackedProduct.objects.select_for_update().get(id=product_id, is_active=True)
    except TrackedProduct.DoesNotExist:
        return f"Target product node {product_id} is missing or flagged inactive."

    html_content = execute_playwright_scrape(product.target_url)
    if not html_content:
        logger.warning('Scrape aborted for product=%s; no HTML content returned.', product.product_name)
        return f"Scraping attempt aborted for product identity: {product.product_name}"

    soup = BeautifulSoup(html_content, 'lxml')
    
    # Pehle try karte hain Shopify ke meta tags se direct raw values nikalne ki (Sabse reliable method!)
    # Meta tags jahan direct content attributes mein price baghair commas/symbols ke hoti hai.
    meta_selectors = [
        'meta[property="og:price:amount"]',
        'meta[property="product:price:amount"]',
        'meta[name="twitter:data1"]'
    ]
    
    extracted_price = None
    for meta_sel in meta_selectors:
        meta_tag = soup.select_one(meta_sel)
        if meta_tag and meta_tag.get('content'):
            parsed_val = parse_price_from_text(meta_tag.get('content'))
            if parsed_val and parsed_val > 10.0:
                extracted_price = parsed_val
                break

    # Agar meta tags se na mile, to HTML selectors par fall back karein
    if not extracted_price:
        price_selectors = [
            '.price--special',                             # Audionic / Shopify Special Price Sale
            '.price-item--sale',                           # Shopify Standard Sale Class
            '.price-item--regular',                        # Shopify Standard Regular Price Class
            'span.pdp-price',                              # Daraz and others
            'span.price--special',                         # Specialized class
            'span.price',                                  # General Span Price
            'div.price',                                   # General Div Price
            '.pdp-product-price',                          # Generic Ecommerce pricing
            '[data-automation="product-price"]'            # Automation tags
        ]
        
        for selector in price_selectors:
            element = soup.select_one(selector)
            if element:
                raw_text = element.get_text()
                parsed_val = parse_price_from_text(raw_text)
                if parsed_val:
                    extracted_price = parsed_val
                    break

    if extracted_price is None:
        logger.warning('Price parse failure for product=%s', product.product_name)
        return f"Failed parsing concrete matching price metric allocations for target: {product.product_name}"

    # Persistent storage engine operations using native ORM interfaces
    now = timezone.now()
    try:
        with transaction.atomic():
            PriceHistory.objects.create(
                product=product,
                price=extracted_price,
                is_available=True,
                scraped_at=now,
            )
            product.last_scraped_at = now
            product.save(update_fields=['last_scraped_at'])
    except DatabaseError as exc:
        logger.exception('Database write failed for product=%s', product.product_name)
        return f"Database write failure for {product.product_name}: {exc}"

    try:
        price_decimal = Decimal(str(extracted_price))
    except (InvalidOperation, TypeError):
        price_decimal = None

    if price_decimal is not None and price_decimal <= product.notification_threshold:
        dispatch_websocket_alert(product, price_decimal)

    return f"Product metrics synchronized successfully: {product.product_name} -> {extracted_price}"

def dispatch_websocket_alert(product, price):
    """Broadcasts clean instant notification streams across operational browser sockets."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning('No channel layer configured; skipping alert dispatch for product=%s', product.product_name)
        return

    group_name = f"user_{product.user.id}_alerts"
    payload = {
        'product_name': product.product_name,
        'current_price': float(price),
        'threshold_target': float(product.notification_threshold),
        'target_url': product.target_url,
        'timestamp': timezone.now().isoformat(),
    }

    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'broadcast.alert',
                'payload': payload,
            }
        )
    except Exception as exc:
        logger.exception('Failed sending websocket alert for product=%s', product.product_name)


@shared_task(name="trackers.tasks.orchestrate_scraping_pipeline")
def orchestrate_scraping_pipeline():
    """Reads inventory rows and drops high-concurrency background subtasks arrays."""
    active_products = TrackedProduct.objects.filter(is_active=True).values_list('id', flat=True)
    
    for product_id in active_products:
        scrape_single_product.delay(product_id)
        
    return f"Dispatched {len(active_products)} product scraping worker routines to the cluster queues."