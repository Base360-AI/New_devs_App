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
  const [propertiesError, setPropertiesError] = useState("");

  useEffect(() => {
    const loadProperties = async () => {
      try {
        const tenantProperties = await SecureAPI.getDashboardProperties();
        setProperties(tenantProperties);
        setSelectedProperty(tenantProperties[0]?.id || "");
      } catch (error) {
        console.error(error);
        setPropertiesError("Failed to load properties");
      }
    };

    loadProperties();
  }, []);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">
          Property Management Dashboard
        </h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">
                  Revenue Overview
                </h2>
                <p className="text-sm lg:text-base text-gray-600">
                  Monthly performance insights for your properties
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <div className="flex flex-col sm:items-end">
                  <label
                    htmlFor="report-month"
                    className="text-xs font-medium text-gray-700 mb-1"
                  >
                    Report Month
                  </label>
                  <input
                    id="report-month"
                    type="month"
                    value={reportMonth}
                    onChange={(event) => setReportMonth(event.target.value)}
                    className="block w-full sm:w-auto px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  />
                </div>

                <div className="flex flex-col sm:items-end">
                  <label
                    htmlFor="property-selector"
                    className="text-xs font-medium text-gray-700 mb-1"
                  >
                    Select Property
                  </label>
                  <select
                    id="property-selector"
                    value={selectedProperty}
                    onChange={(event) =>
                      setSelectedProperty(event.target.value)
                    }
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
          </div>

          {propertiesError && (
            <div className="p-4 text-red-500 bg-red-50 rounded-lg">
              {propertiesError}
            </div>
          )}
          {!propertiesError && selectedProperty && (
            <div className="space-y-6">
              <RevenueSummary
                propertyId={selectedProperty}
                reportMonth={reportMonth}
              />
            </div>
          )}
          {!propertiesError && !selectedProperty && (
            <div className="p-4 text-gray-500 bg-gray-50 rounded-lg">
              No properties available
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
