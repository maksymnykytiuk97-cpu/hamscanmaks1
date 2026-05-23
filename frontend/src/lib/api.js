import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

// Create axios instance with credentials
export const api = axios.create({
  baseURL: BACKEND_URL,
  withCredentials: true,
});

// Helper to format API errors
export function formatApiErrorDetail(detail) {
  if (detail == null) return "Что-то пошло не так. Попробуйте снова.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
