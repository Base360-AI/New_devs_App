import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

const REPORT_MONTH = 3;
const REPORT_YEAR = 2024;

interface PropertyOption {
  id: string;
  name: string;
  timezone: string;
}

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<PropertyOption[]>([]);
  const [selectedProperty, setSelectedProperty] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;
    SecureAPI.getProperties()
      .then((response) => {
        if (cancelled) return;
        const list = response.data || [];
        setProperties(list);
        setSelectedProperty(list[0]?.id ?? "");
      })
      .catch((err) => {
        console.error(err);
        if (!cancelled) setLoadError("Failed to load properties");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">Revenue Overview</h2>
                <p className="text-sm lg:text-base text-gray-600">
                  March 2024 performance for your properties, using each property&apos;s local time zone
                </p>
              </div>

              <div className="flex flex-col sm:items-end">
                <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  value={selectedProperty}
                  onChange={(e) => setSelectedProperty(e.target.value)}
                  disabled={properties.length === 0}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                >
                  {properties.map((property) => (
                    <option key={property.id} value={property.id}>
                      {property.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {loadError && <div className="p-4 text-red-500 bg-red-50 rounded-lg">{loadError}</div>}
          {!loadError && selectedProperty && (
            <div className="space-y-6">
              <RevenueSummary
                propertyId={selectedProperty}
                month={REPORT_MONTH}
                year={REPORT_YEAR}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;