import React, { useEffect, useState } from "react";
import { SecureAPI } from "../lib/secureApi";
import { RevenueSummary } from "./RevenueSummary";

interface DashboardProperty {
  id: string;
  name: string;
  timezone: string;
}

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<DashboardProperty[]>([]);
  const [selectedProperty, setSelectedProperty] = useState("");
  const [propertiesLoading, setPropertiesLoading] = useState(true);
  const [propertiesError, setPropertiesError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const fetchProperties = async () => {
      setPropertiesLoading(true);
      setPropertiesError("");

      try {
        const tenantProperties = await SecureAPI.getDashboardProperties();
        if (cancelled) return;

        setProperties(tenantProperties);
        setSelectedProperty((currentProperty) => {
          if (tenantProperties.some((property) => property.id === currentProperty)) {
            return currentProperty;
          }
          return tenantProperties[0]?.id ?? "";
        });
      } catch (error) {
        if (!cancelled) {
          setPropertiesError("Failed to load properties");
          console.error(error);
        }
      } finally {
        if (!cancelled) setPropertiesLoading(false);
      }
    };

    fetchProperties();
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
                  Monthly performance insights for your properties
                </p>
              </div>

              <div className="flex flex-col sm:items-end">
                <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  value={selectedProperty}
                  onChange={(event) => setSelectedProperty(event.target.value)}
                  disabled={propertiesLoading || properties.length === 0}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm disabled:bg-gray-100"
                >
                  {propertiesLoading && <option value="">Loading properties...</option>}
                  {!propertiesLoading && properties.length === 0 && (
                    <option value="">No properties available</option>
                  )}
                  {properties.map((property) => (
                    <option key={property.id} value={property.id}>
                      {property.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {propertiesError && (
            <div className="p-4 text-red-500 bg-red-50 rounded-lg">{propertiesError}</div>
          )}

          {!propertiesError && selectedProperty && (
            <div className="space-y-6">
              <RevenueSummary propertyId={selectedProperty} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
