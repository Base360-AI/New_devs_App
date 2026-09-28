import React, { useEffect, useMemo, useState } from "react";

import { SecureAPI } from "../lib/secureApi";

interface RevenueData {
  property_id: string;
  property_name: string;
  year: number;
  month: number;
  timezone: string;
  total_revenue: string;
  currency: string;
  reservations_count: number;
}

interface RevenueSummaryProps {
  propertyId: string;
  reportMonth: string;
}

function formatExactMoney(amount: string): string {
  const [rawWhole, rawFraction = ""] = amount.split(".");
  const isNegative = rawWhole.startsWith("-");
  const whole = (isNegative ? rawWhole.slice(1) : rawWhole) || "0";
  const groupedWhole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const fraction = rawFraction.padEnd(2, "0").slice(0, 2);

  return `${isNegative ? "-" : ""}${groupedWhole}.${fraction}`;
}

function formatReportMonth(value: string): string {
  const [year, month] = value.split("-").map(Number);
  if (!year || !month) return "Selected month";

  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC"
  }).format(new Date(Date.UTC(year, month - 1, 1)));
}

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId, reportMonth }) => {
  const [data, setData] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const period = useMemo(() => {
    const [year, month] = reportMonth.split("-").map(Number);
    return { year, month };
  }, [reportMonth]);

  useEffect(() => {
    let isCurrent = true;

    const fetchRevenue = async () => {
      if (!period.year || !period.month) {
        setData(null);
        setError("Choose a valid report month.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const response = await SecureAPI.getDashboardSummary(propertyId, period);
        if (isCurrent) setData(response);
      } catch (requestError) {
        if (isCurrent) {
          console.error(requestError);
          setData(null);
          setError("Failed to load revenue data.");
        }
      } finally {
        if (isCurrent) setLoading(false);
      }
    };

    fetchRevenue();
    return () => {
      isCurrent = false;
    };
  }, [period, propertyId]);

  if (loading) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-100 rounded w-1/4" />
          <div className="h-8 bg-gray-100 rounded w-1/2" />
          <div className="flex gap-4 pt-4">
            <div className="h-12 bg-gray-100 rounded flex-1" />
            <div className="h-12 bg-gray-100 rounded flex-1" />
          </div>
        </div>
      </div>
    );
  }

  if (error) return <div className="p-4 text-red-700 bg-red-50 rounded-lg">{error}</div>;
  if (!data) return null;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-300">
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
              {formatReportMonth(reportMonth)} Revenue
            </h2>
            <p className="text-xs text-gray-500 mt-1">Property-local reporting time: {data.timezone}</p>
            <div className="mt-1">
              <span className="text-3xl font-bold text-gray-900 tracking-tight">
                {data.currency} {formatExactMoney(data.total_revenue)}
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
          <div>
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Property</p>
            <p className="text-sm font-semibold text-gray-700 mt-1">{data.property_name}</p>
            <p className="text-xs text-gray-500 font-mono mt-1">{data.property_id}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Reservations</p>
            <p className="text-sm font-semibold text-gray-700 mt-1">
              {data.reservations_count} <span className="font-normal text-gray-400">bookings</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
