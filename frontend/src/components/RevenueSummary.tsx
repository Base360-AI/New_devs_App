import React, { useEffect, useState } from "react";
import { SecureAPI } from "../lib/secureApi";

interface RevenueData {
  property_id: string;
  tenant_id: string;
  total_revenue: string;
  currency: string;
}

interface RevenueSummaryProps {
  propertyId?: string;
  month?: number;
  year?: number;
  showRaw?: boolean;
}

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({
  propertyId = "prop-001",
  month,
  year,
  showRaw = false,
}) => {
  const currentDate = new Date();

  const reportMonth = month ?? currentDate.getMonth() + 1;
  const reportYear = year ?? currentDate.getFullYear();

  const [data, setData] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchRevenue = async () => {
      setLoading(true);
      setError("");

      try {
        const response = await SecureAPI.getDashboardSummary(
          propertyId,
          reportMonth,
          reportYear
        );

        setData(response);
      } catch (requestError) {
        console.error(requestError);
        setError("Failed to load revenue data");
      } finally {
        setLoading(false);
      }
    };

    fetchRevenue();
  }, [propertyId, reportMonth, reportYear]);

  if (loading) {
    return <div className="p-6">Loading revenue...</div>;
  }

  if (error) {
    return (
      <div className="p-4 text-red-500 bg-red-50 rounded-lg">
        {error}
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const formattedTotal = Number(data.total_revenue).toLocaleString(
    undefined,
    {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }
  );

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      {showRaw && (
        <pre className="p-3 bg-gray-50 text-xs overflow-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}

      <div className="p-6">
        <h2 className="text-sm font-medium text-gray-500 uppercase">
          Monthly Revenue
        </h2>

        <p className="mt-2 text-3xl font-bold text-gray-900">
          {data.currency} {formattedTotal}
        </p>

        <p className="mt-4 text-sm text-gray-500">
          {reportMonth}/{reportYear}
        </p>

        <p className="mt-2 text-xs text-gray-500">
          Property: {data.property_id}
        </p>
      </div>
    </div>
  );
};