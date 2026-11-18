import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

type PropertyOption = { id: string; name: string };

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<PropertyOption[]>([]);
  const [selectedProperty, setSelectedProperty] = useState("");
  const [month, setMonth] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    SecureAPI.getDashboardProperties()
      .then((result) => {
        if (!active) return;
        setProperties(result);
        setSelectedProperty(result[0]?.id ?? "");
      })
      .catch((err) => {
        console.error("Failed to load tenant properties", err);
        if (active) setError("Failed to load your properties");
      });
    return () => { active = false; };
  }, []);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6 flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
            <div>
              <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">Revenue Overview</h2>
              <p className="text-sm lg:text-base text-gray-600">Monthly performance insights for your properties</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <label className="flex flex-col text-xs font-medium text-gray-700 gap-1">
                Select Property
                <select value={selectedProperty} onChange={(e) => setSelectedProperty(e.target.value)} disabled={!properties.length}
                  className="min-w-[200px] px-3 py-2 border border-gray-300 rounded-md text-sm">
                  {properties.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}
                </select>
              </label>
              <label className="flex flex-col text-xs font-medium text-gray-700 gap-1">
                Reporting Month
                <input type="month" value={month} onChange={(e) => setMonth(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-md text-sm" />
              </label>
            </div>
          </div>
          {error && <p role="alert" className="mb-4 p-3 text-red-700 bg-red-50 rounded">{error}</p>}
          {properties.length === 0 && !error && <p className="text-gray-600">Loading your properties…</p>}
          {selectedProperty && <RevenueSummary propertyId={selectedProperty} month={month || undefined} />}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
