import { useQuery } from '@tanstack/react-query';
import { analyticsService, type AnalyticsSummary } from '@/services/api';

export const analyticsQueryKey = ['analytics-summary'];

export const useAnalyticsSummary = () =>
  useQuery<AnalyticsSummary>({
    queryKey: analyticsQueryKey,
    queryFn: async () => {
      const response = await analyticsService.getSummary();
      return response.data;
    },
    staleTime: 30_000,
  });
