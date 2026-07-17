import { useQuery } from '@tanstack/react-query';
import { trackerService } from '@/services/api';

export const useProducts = () =>
  useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      const response = await trackerService.listProducts();
      return response.data;
    },
  });
