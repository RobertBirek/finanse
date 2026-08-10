import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: "active" | "on_hold" | "completed" | "cancelled";
  deadline: string | null;
  color: string | null;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  user_id: string;
  project_id: string | null;
  title: string;
  description: string | null;
  status: "todo" | "in_progress" | "done" | "cancelled";
  priority: "low" | "medium" | "high" | "urgent";
  due_date: string | null;
  estimated_minutes: number | null;
  actual_minutes: number | null;
  completed_at: string | null;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface TimeBlock {
  id: string;
  user_id: string;
  task_id: string | null;
  project_id: string | null;
  title: string;
  start_time: string;
  end_time: string;
  block_type: "deep_work" | "shallow" | "meeting" | "break";
  created_at: string;
  updated_at: string;
}

export function useProjects(params?: { status?: string }) {
  return useQuery({
    queryKey: ["work", "projects", params],
    queryFn: async () => {
      const { data } = await api.get<Project[]>("/work/projects", { params });
      return data;
    },
  });
}

export function useProject(id: string | null) {
  return useQuery({
    queryKey: ["work", "projects", id],
    queryFn: async () => {
      const { data } = await api.get<Project>(`/work/projects/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (project: { name: string; description?: string; status?: string; deadline?: string; color?: string }) => {
      const { data } = await api.post<Project>("/work/projects", project);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work", "projects"] });
    },
  });
}

export function useTasks(params?: {
  project_id?: string;
  status?: string;
  due_date?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["work", "tasks", params],
    queryFn: async () => {
      const { data } = await api.get<Task[]>("/work/tasks", { params });
      return data;
    },
  });
}

export function useTask(id: string | null) {
  return useQuery({
    queryKey: ["work", "tasks", id],
    queryFn: async () => {
      const { data } = await api.get<Task>(`/work/tasks/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

export function useCreateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (task: {
      project_id?: string;
      title: string;
      description?: string;
      priority?: string;
      due_date?: string;
      estimated_minutes?: number;
    }) => {
      const { data } = await api.post<Task>("/work/tasks", task);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work", "tasks"] });
    },
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      ...task
    }: {
      id: string;
      title?: string;
      status?: string;
      priority?: string;
      project_id?: string;
      due_date?: string;
      estimated_minutes?: number;
      actual_minutes?: number;
    }) => {
      const { data } = await api.patch<Task>(`/work/tasks/${id}`, task);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work", "tasks"] });
    },
  });
}

export function useTimeBlocks(params?: {
  start_time?: string;
  end_time?: string;
  task_id?: string;
  project_id?: string;
}) {
  return useQuery({
    queryKey: ["work", "time_blocks", params],
    queryFn: async () => {
      const { data } = await api.get<TimeBlock[]>("/work/time-blocks", { params });
      return data;
    },
  });
}

export function useCreateTimeBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (block: {
      task_id?: string;
      project_id?: string;
      title?: string;
      start_time: string;
      end_time: string;
      block_type?: string;
    }) => {
      const { data } = await api.post<TimeBlock>("/work/time-blocks", block);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work", "time_blocks"] });
    },
  });
}
