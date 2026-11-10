import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface DashboardProperty {
  id: string;
  name: string;
  timezone: string;
}

const Dashboard: React.FC = () => {
  // Properties come from the backend for the logged-in tenant only, so one
  // client never sees another client's property names.
  const [properties, setProperties] = useState<DashboardProperty[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertiesError, setPropertiesError] = useState('');
  // "YYYY-MM" from <input type="month">, or "" for all time.
  const [period, setPeriod] = useState('');
  const [periodYear, periodMonth] = period ? period.split('-').map(Number) : [undefined, undefined];

  useEffect(() => {
    let cancelled = false;
    SecureAPI.getDashboardProperties()
      .then((list) => {
        if (cancelled) return;
        setProperties(list);
        setSelectedProperty(list[0]?.id ?? '');
      })
      .catch((err) => {
        console.error(err);
        if (!cancelled) setPropertiesError('Failed to load properties');
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
              
              <div className="flex flex-col sm:flex-row gap-4">
              {/* Month filter (calendar month in each property's own timezone) */}
              <div className="flex flex-col sm:items-end">
                <label htmlFor="revenue-month" className="text-xs font-medium text-gray-700 mb-1">
                  Month (property local time)
                </label>
                <div className="flex gap-2">
                  <input
                    id="revenue-month"
                    type="month"
                    value={period}
                    onChange={(e) => setPeriod(e.target.value)}
                    className="block px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  />
                  {period && (
                    <button
                      type="button"
                      onClick={() => setPeriod('')}
                      className="px-3 py-2 text-sm whitespace-nowrap text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
                    >
                      All time
                    </button>
                  )}
                </div>
              </div>

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
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {propertiesError && (
              <div className="p-4 text-red-500 bg-red-50 rounded-lg">{propertiesError}</div>
            )}
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
