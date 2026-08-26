import React, { useEffect, useState } from "react";
import { SecureAPI } from "../lib/secureApi";

interface RevenueData {
  property_id: string;
  month: number;
  year: number;
  total_revenue: string;
  currency: string;
  reservations_count: number;
}

interface RevenueSummaryProps {
  propertyId: string;
  month: number;
  year: number;
  showRaw?: boolean;
}

const formatMoney = (amount: string): string => {
  const isNegative = amount.startsWith("-");
  const unsigned = isNegative ? amount.slice(1) : amount;
  const [whole, fraction = "00"] = unsigned.split(".");
  const groupedWhole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${isNegative ? "-" : ""}${groupedWhole}.${fraction.padEnd(2, "0").slice(0, 2)}`;
};

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({
  propertyId,
  month,
  year,
  showRaw,
}) => {
  const [data, setData] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;

    const fetchRevenue = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await SecureAPI.getDashboardSummary(
          propertyId,
          month,
          year,
        );
        if (!ignore) setData(response);
      } catch (err) {
        if (!ignore) setError("Failed to load revenue data");
        console.error(err);
      } finally {
        if (!ignore) setLoading(false);
      }
    };

    fetchRevenue();
    return () => {
      ignore = true;
    };
  }, [propertyId, month, year]);

  if (loading) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-100 rounded w-1/4"></div>
          <div className="h-8 bg-gray-100 rounded w-1/2"></div>
          <div className="flex gap-4 pt-4">
            <div className="h-12 bg-gray-100 rounded flex-1"></div>
            <div className="h-12 bg-gray-100 rounded flex-1"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error)
    return <div className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>;
  if (!data) return null;

  const periodLabel = new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
  }).format(new Date(data.year, data.month - 1, 1));

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-300">
      {showRaw && (
        <div className="p-3 bg-gray-50 text-xs font-mono border-b border-gray-100 overflow-auto max-h-32">
          <strong className="block mb-1 text-gray-500 uppercase tracking-wider text-[10px]">
            Raw API Response
          </strong>
          <pre className="text-gray-700">{JSON.stringify(data, null, 2)}</pre>
        </div>
      )}

      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
            {periodLabel} Revenue
          </h2>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-bold text-gray-900 tracking-tight">
              {data.currency} {formatMoney(data.total_revenue)}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
          <div>
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
              Property ID
            </p>
            <p className="text-sm font-semibold text-gray-700 font-mono mt-1">
              {data.property_id}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
              Reservations
            </p>
            <p className="text-sm font-semibold text-gray-700 mt-1">
              {data.reservations_count}{" "}
              <span className="font-normal text-gray-400">bookings</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
