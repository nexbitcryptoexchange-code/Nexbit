import axios from "axios";

const BASE = process.env.REACT_APP_BACKEND_URL;
export const API_URL = `${BASE}/api`;

export const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const data = err?.response?.data;
    if (data && Array.isArray(data.detail)) {
      err.message = data.detail.map((e) => e.msg || JSON.stringify(e)).join(" ");
    } else if (data && typeof data.detail === "string") {
      err.message = data.detail;
    }
    return Promise.reject(err);
  }
);

export const fmtUsd = (n, digits = 2) => {
  if (n === null || n === undefined || isNaN(n)) return "--";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(2)}K`;
  return `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
};

export const fmtNum = (n, digits = 4) => {
  if (n === null || n === undefined || isNaN(n)) return "--";
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: digits });
};

export const fmtPrice = (n) => {
  if (!n) return "--";
  if (n >= 1000) return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n >= 1) return n.toFixed(4);
  return n.toFixed(6);
};

export const fmtPct = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "--";
  const s = n >= 0 ? "+" : "";
  return `${s}${Number(n).toFixed(2)}%`;
};

export const fmtTime = (iso) => {
  if (!iso) return "--";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};
