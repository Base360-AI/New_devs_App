import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
}

const Dashboard: React.FC = () => {
  // Only the logged-in tenant's own properties are offered (property ids are not unique across tenants)
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [loadingProperties, setLoadingProperties] = useState(true);
  const [propertiesError, setPropertiesError] = useState('');

  useEffect(() => {
    let cancelled = false;
    SecureAPI.getDashboardProperties()
      .then((res) => {
        if (cancelled) return;
        setProperties(res.properties);
        setSelectedProperty(res.properties[0]?.id ?? '');
      })
      .catch((err) => {
        console.error(err);
        if (!cancelled) setPropertiesError('Failed to load properties');
      })
      .finally(() => {
        if (!cancelled) setLoadingProperties(false);
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
                  Monthly performance insights for your properties
                </p>
              </div>
              
              {/* Property Selector */}
              <div className="flex flex-col sm:items-end">
                <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  value={selectedProperty}
                  onChange={(e) => setSelectedProperty(e.target.value)}
                  disabled={loadingProperties || properties.length === 0}
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

          <div className="space-y-6">
            {loadingProperties && (
              <div className="text-sm text-gray-500">Loading properties...</div>
            )}
            {propertiesError && (
              <div className="p-4 text-red-500 bg-red-50 rounded-lg">{propertiesError}</div>
            )}
            {!loadingProperties && !propertiesError && properties.length === 0 && (
              <div className="text-sm text-gray-500">No properties found for your account.</div>
            )}
            {selectedProperty && <RevenueSummary propertyId={selectedProperty} />}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
