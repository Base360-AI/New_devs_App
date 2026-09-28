import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { BookingsList } from "./BookingsList";
import { SecureAPI } from "../lib/secureApi";

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<{ id: string; name: string }[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [selectedMonth, setSelectedMonth] = useState(''); // "YYYY-MM", empty = all time
  const [error, setError] = useState('');

  useEffect(() => {
    SecureAPI.getDashboardProperties()
      .then((res) => {
        setProperties(res.properties);
        if (res.properties.length) setSelectedProperty(res.properties[0].id);
      })
      .catch((err) => {
        console.error(err);
        setError('Failed to load properties');
      });
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
                <label className="text-xs font-medium text-gray-700 mb-1">Month</label>
                <input
                  type="month"
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(e.target.value)}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 mb-3 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                />
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

          <div className="space-y-6">
            {error && <div className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>}
            {selectedProperty && <RevenueSummary propertyId={selectedProperty} month={selectedMonth} />}
            {selectedProperty && <BookingsList propertyId={selectedProperty} month={selectedMonth} />}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
