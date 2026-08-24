import React, { useEffect, useState } from "react";
import { SecureAPI } from "../lib/secureApi";
import { RevenueSummary } from "./RevenueSummary";

interface Property {
  id: string;
  name: string;
}

const Dashboard: React.FC = () => {
  const [selectedProperty, setSelectedProperty] = useState('');
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadProperties = async () => {
      try {
        const result = await SecureAPI.getAllProperties();
        const tenantProperties = result.data || [];

        setProperties(tenantProperties);

        if (tenantProperties.length > 0) {
          setSelectedProperty(tenantProperties[0].id);
        }
      } catch (err) {
        console.error("Failed to load properties:", err);
        setError("Unable to load properties");
      } finally {
        setLoading(false);
      }
    };

    loadProperties();
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
                  disabled={loading || properties.length === 0}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                >
                  {loading && (
                    <option value="">Loading properties...</option>
                  )}

                  {!loading && properties.length === 0 && (
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
          {error && (
            <div className="text-red-600 mb-4">
              {error}
            </div>
          )}
          <div className="space-y-6">
          {selectedProperty && (
              <RevenueSummary propertyId={selectedProperty} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
