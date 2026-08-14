import React, { useEffect, useState } from "react";
import { SecureAPI } from "../lib/secureApi";
import type { DashboardProperty } from "../lib/secureApi";
import { RevenueSummary } from "./RevenueSummary";

const REPORT_YEAR = 2024;
const REPORT_MONTH = 3;

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<DashboardProperty[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertiesLoading, setPropertiesLoading] = useState(true);
  const [propertiesError, setPropertiesError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const fetchProperties = async () => {
      setPropertiesLoading(true);
      setPropertiesError('');

      try {
        const tenantProperties = await SecureAPI.getDashboardProperties();

        if (!cancelled) {
          setProperties(tenantProperties);
          setSelectedProperty(tenantProperties[0]?.id ?? '');
        }
      } catch (error) {
        console.error('Failed to load dashboard properties', error);
        if (!cancelled) {
          setProperties([]);
          setSelectedProperty('');
          setPropertiesError('Failed to load properties');
        }
      } finally {
        if (!cancelled) {
          setPropertiesLoading(false);
        }
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
              
              {!propertiesLoading && !propertiesError && properties.length > 0 && (
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                  <select
                    value={selectedProperty}
                    onChange={(e) => setSelectedProperty(e.target.value)}
                    className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {properties.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-6">
            {propertiesLoading && (
              <div className="p-4 text-gray-600 bg-gray-50 rounded-lg">Loading properties...</div>
            )}
            {propertiesError && (
              <div className="p-4 text-red-600 bg-red-50 rounded-lg">{propertiesError}</div>
            )}
            {!propertiesLoading && !propertiesError && properties.length === 0 && (
              <div className="p-4 text-gray-600 bg-gray-50 rounded-lg">No properties are available for this account.</div>
            )}
            {selectedProperty && (
              <RevenueSummary
                key={selectedProperty}
                propertyId={selectedProperty}
                year={REPORT_YEAR}
                month={REPORT_MONTH}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
