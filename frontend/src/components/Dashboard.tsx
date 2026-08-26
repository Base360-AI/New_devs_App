import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
  timezone: string;
}

// BUG FIX: the property list used to be hard-coded with all five properties (from both
// tenants), so Ocean Rentals saw Sunset's property names and vice-versa. Properties are
// now loaded from the tenant-scoped /dashboard/properties endpoint.
const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState<string>('');
  const [period, setPeriod] = useState<string>(''); // '' = all time, otherwise 'YYYY-MM'
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    let cancelled = false;
    SecureAPI.getDashboardProperties()
      .then((list: Property[]) => {
        if (cancelled) return;
        setProperties(list);
        setSelectedProperty(prev => (list.some(p => p.id === prev) ? prev : (list[0]?.id ?? '')));
      })
      .catch((err: unknown) => {
        console.error(err);
        if (!cancelled) setLoadError('Failed to load properties');
      });
    return () => { cancelled = true; };
  }, []);

  const [periodYear, periodMonth] = period ? period.split('-').map(Number) : [undefined, undefined];

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

              <div className="flex flex-col sm:flex-row gap-3">
                {/* Property Selector */}
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
                        {property.name} ({property.timezone})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Period Selector: month is interpreted in the property's timezone */}
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Period</label>
                  <div className="flex gap-2">
                    <input
                      type="month"
                      value={period}
                      onChange={(e) => setPeriod(e.target.value)}
                      className="block px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                    />
                    {period && (
                      <button
                        type="button"
                        onClick={() => setPeriod('')}
                        className="px-3 py-2 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
                      >
                        All time
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {loadError && <div className="p-4 text-red-500 bg-red-50 rounded-lg">{loadError}</div>}
            {selectedProperty && (
              <RevenueSummary propertyId={selectedProperty} month={periodMonth} year={periodYear} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
