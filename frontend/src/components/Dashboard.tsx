import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
  timezone?: string;
}

const Dashboard: React.FC = () => {
  // The list is per-tenant: property ids are unique only within a tenant
  // (prop-001 belongs to two different clients), so it has to come from the
  // backend rather than a constant shared by every user.
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertiesError, setPropertiesError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadProperties = async () => {
      try {
        const response = await SecureAPI.getProperties();
        const list: Property[] = response?.data ?? [];
        if (cancelled) return;
        setProperties(list);
        setSelectedProperty((current) =>
          list.some((p) => p.id === current) ? current : list[0]?.id ?? ''
        );
      } catch (err) {
        if (cancelled) return;
        console.error('[Dashboard] Failed to load properties', err);
        setPropertiesError('Failed to load properties');
      }
    };

    loadProperties();
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
                  disabled={properties.length === 0}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {properties.length === 0 && (
                    <option value="">
                      {propertiesError || 'Loading properties…'}
                    </option>
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

          <div className="space-y-6">
            {propertiesError ? (
              <div className="p-4 text-red-500 bg-red-50 rounded-lg">{propertiesError}</div>
            ) : selectedProperty ? (
              <RevenueSummary propertyId={selectedProperty} />
            ) : (
              <div className="p-4 text-gray-500">Loading properties…</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
