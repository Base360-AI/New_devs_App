import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
}

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[] | null>(null);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertiesError, setPropertiesError] = useState('');
  const [month, setMonth] = useState(3);
  const [year, setYear] = useState(2024);

  useEffect(() => {
    SecureAPI.getDashboardProperties()
      .then((result: Property[]) => {
        setProperties(result);
        setSelectedProperty(result[0]?.id || '');
      })
      .catch(() => setPropertiesError('Failed to load properties'));
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
              
              <div className="flex flex-wrap gap-3 sm:justify-end">
                <div className="flex flex-col">
                  <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                  <select
                    value={selectedProperty}
                    onChange={(e) => setSelectedProperty(e.target.value)}
                    className="block min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {properties?.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col">
                  <label className="text-xs font-medium text-gray-700 mb-1">Month</label>
                  <select
                    value={month}
                    onChange={(e) => setMonth(Number(e.target.value))}
                    className="px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {Array.from({ length: 12 }, (_, index) => index + 1).map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col">
                  <label className="text-xs font-medium text-gray-700 mb-1">Year</label>
                  <input
                    type="number"
                    min="1"
                    max="9998"
                    value={year}
                    onChange={(e) => setYear(Number(e.target.value))}
                    className="w-24 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {propertiesError && <div className="text-red-500">{propertiesError}</div>}
            {!propertiesError && properties?.length === 0 && <div>No properties available.</div>}
            {selectedProperty && (
              <RevenueSummary propertyId={selectedProperty} year={year} month={month} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
