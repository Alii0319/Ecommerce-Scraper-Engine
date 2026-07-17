import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { trackerService, type TrackedProduct } from '@/services/api';

export interface TrackerCreatePayload {
  product_name: string;
  target_url: string;
  notification_threshold: number;
  is_active: boolean;
}

export const trackersQueryKey = ['trackers'];

export const useTrackersList = () =>
  useQuery<TrackedProduct[]>({
    queryKey: trackersQueryKey,
    queryFn: async () => {
      const response = await trackerService.listProducts();
      return response.data;
    },
    staleTime: 60_000,
  });

export const useCreateTracker = () => {
  const queryClient = useQueryClient();

  return useMutation<TrackedProduct, Error, TrackerCreatePayload>({
    mutationFn: async (payload) => {
      const response = await trackerService.createProduct(payload);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: trackersQueryKey });
    },
  });
};

interface DeleteTrackerContext {
  previousTrackers: TrackedProduct[] | undefined;
}

export const useDeleteTracker = () => {
  const queryClient = useQueryClient();

  return useMutation<void, Error, number, DeleteTrackerContext>({
    mutationFn: async (trackerId) => {
      await trackerService.deleteProduct(trackerId);
    },
    onMutate: async (trackerId) => {
      await queryClient.cancelQueries({ queryKey: trackersQueryKey });
      const previousTrackers = queryClient.getQueryData<TrackedProduct[]>(trackersQueryKey);

      if (previousTrackers) {
        queryClient.setQueryData<TrackedProduct[]>(trackersQueryKey, (current = []) =>
          current.filter((tracker) => tracker.id !== trackerId),
        );
      }

      return { previousTrackers };
    },
    onError: (_error, _trackerId, context) => {
      if (context?.previousTrackers) {
        queryClient.setQueryData(trackersQueryKey, context.previousTrackers);
      }
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: trackersQueryKey });
    },
  });
};
