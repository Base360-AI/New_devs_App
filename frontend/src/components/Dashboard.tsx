import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
  timezone: string;
}

const Dashboard: React.FC = () => {
  // Properties come from the API scoped to the caller's tenant. The list used
  // to be hardcoded with every tenant's properties, which both exposed other
  // clients' portfolios and let users request revenue they cannot see.
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [period, setPeriod] = useState('2024-03');
  const [showRaw, setShowRaw] = useState(false);
  const [propertiesError, setPropertiesError] = useState('');

  useEffect(() => {
    const loadProperties = async () => {
      try {
        const list = await SecureAPI.getDashboardProperties();
        setProperties(list);
        setSelectedProperty((current) => current || list[0]?.id || '');
      } catch (err) {
        setPropertiesError('Failed to load properties');
        console.error(err);
      }
    };

    loadProperties();
  }, []);

  const [year, month] = period ? period.split('-').map(Number) : [undefined, undefined];

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

              <div className="flex flex-col sm:flex-row gap-4">
                {/* Property Selector */}
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

                {/* Period Selector */}
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Period</label>
                  <div className="flex gap-2">
                    <input
                      type="month"
                      value={period}
                      onChange={(e) => setPeriod(e.target.value)}
                      className="block px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => setPeriod('')}
                      className="px-3 py-2 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                    >
                      All time
                    </button>
                  </div>
                  <label className="flex items-center gap-1.5 text-xs text-gray-500 mt-2">
                    <input
                      type="checkbox"
                      checked={showRaw}
                      onChange={(e) => setShowRaw(e.target.checked)}
                      className="rounded border-gray-300"
                    />
                    Show raw API response
                  </label>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {propertiesError && (
              <div className="p-4 text-red-500 bg-red-50 rounded-lg">{propertiesError}</div>
            )}
            {!propertiesError && properties.length === 0 && (
              <div className="p-4 text-gray-500 bg-gray-50 rounded-lg">No properties available for your account.</div>
            )}
            {selectedProperty && (
              <RevenueSummary propertyId={selectedProperty} month={month} year={year} showRaw={showRaw} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
