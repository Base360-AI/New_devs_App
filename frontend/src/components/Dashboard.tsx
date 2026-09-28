import React, { useEffect, useState } from "react";

import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface DashboardProperty {
  id: string;
  name: string;
  timezone: string;
}

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<DashboardProperty[]>([]);
  const [selectedProperty, setSelectedProperty] = useState("");
  const [reportMonth, setReportMonth] = useState("2024-03");
  const [loadingProperties, setLoadingProperties] = useState(true);
  const [propertiesError, setPropertiesError] = useState("");

  useEffect(() => {
    let isCurrent = true;

    const loadProperties = async () => {
      setLoadingProperties(true);
      setPropertiesError("");

      try {
        const response = await SecureAPI.getDashboardProperties();
        if (!isCurrent) return;

        const tenantProperties = response.items || [];
        setProperties(tenantProperties);
        setSelectedProperty((current) =>
          tenantProperties.some((property) => property.id === current)
            ? current
            : tenantProperties[0]?.id || ""
        );
      } catch (error) {
        if (!isCurrent) return;
        console.error(error);
        setPropertiesError("Failed to load your properties.");
      } finally {
        if (isCurrent) setLoadingProperties(false);
      }
    };

    loadProperties();
    return () => {
      isCurrent = false;
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
                  Monthly performance insights for your properties
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
                <div className="flex flex-col sm:items-end">
                  <label htmlFor="dashboard-property" className="text-xs font-medium text-gray-700 mb-1">
                    Select Property
                  </label>
                  <select
                    id="dashboard-property"
                    value={selectedProperty}
                    disabled={loadingProperties || properties.length === 0}
                    onChange={(event) => setSelectedProperty(event.target.value)}
                    className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                  >
                    {loadingProperties && <option>Loading properties…</option>}
                    {!loadingProperties && properties.length === 0 && <option>No properties available</option>}
                    {properties.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col sm:items-end">
                  <label htmlFor="dashboard-month" className="text-xs font-medium text-gray-700 mb-1">
                    Report Month
                  </label>
                  <input
                    id="dashboard-month"
                    type="month"
                    value={reportMonth}
                    onChange={(event) => setReportMonth(event.target.value)}
                    className="block w-full sm:w-auto px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  />
                </div>
              </div>
            </div>
          </div>

          {propertiesError && (
            <div className="p-4 text-red-700 bg-red-50 rounded-lg">{propertiesError}</div>
          )}

          {!propertiesError && !loadingProperties && !selectedProperty && (
            <div className="p-4 text-gray-600 bg-gray-50 rounded-lg">No properties are assigned to this tenant.</div>
          )}

          {selectedProperty && (
            <div className="space-y-6">
              <RevenueSummary propertyId={selectedProperty} reportMonth={reportMonth} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
