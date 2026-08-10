import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: "active" | "on_hold" | "completed" | "archived";
  deadline: string | null;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  project_id: string | null;
  title: string;
  description: string | null;
  status: "todo" | "in_progress" | "done" | "blocked";
  priority: "low" | "medium" | "high" | "urgent";
  due_date: string | null;
  estimated_hours: number | null;
  created_at: string;
}

export interface TimeBlock {
  id: string;
  task_id: string | null;
  project_id: string | null;
  title: string;
  start_time: string;
  end_time: string;
  is_completed: boolean;
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
    mutationFn: async (project: {
      name: string;
      description?: string;
      deadline?: string;
    }) => {
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
      due_date?: string;
    }) => {
      const { data } = await api.patch<Task>(`/work/tasks/${id}`, task);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work", "tasks"] });
      queryClient.invalidateQueries({ queryKey: ["work", "projects"] });
    },
  });
}

export function useTimeBlocks(params?: {
  date?: string;
  project_id?: string;
}) {
  return useQuery({
    queryKey: ["work", "timeblocks", params],
    queryFn: async () => {
      const { data } = await api.get<TimeBlock[]>("/work/timeblocks", { params });
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
      title: string;
      start_time: string;
      end_time: string;
    }) => {
      const { data } = await api.post<TimeBlock>("/work/timeblocks", block);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work", "timeblocks"] });
    },
  });
}
