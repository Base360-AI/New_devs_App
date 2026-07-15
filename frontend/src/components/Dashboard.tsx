import React, { useState, useEffect } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from '../lib/secureApi';

interface Property {
  id: string;
  name: string;
}

const MONTHS = [
  { value: 0, label: 'All time' },
  { value: 1, label: 'January' },
  { value: 2, label: 'February' },
  { value: 3, label: 'March' },
  { value: 4, label: 'April' },
  { value: 5, label: 'May' },
  { value: 6, label: 'June' },
  { value: 7, label: 'July' },
  { value: 8, label: 'August' },
  { value: 9, label: 'September' },
  { value: 10, label: 'October' },
  { value: 11, label: 'November' },
  { value: 12, label: 'December' },
];

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [selectedMonth, setSelectedMonth] = useState(0);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadProperties = async () => {
      try {
        const result = await SecureAPI.getProperties();
        const items = result.data || [];
        setProperties(items);
        if (items.length > 0) {
          setSelectedProperty(items[0].id);
        }
      } catch (error) {
        console.error('Failed to load properties:', error);
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

              <div className="flex flex-col sm:flex-row gap-3">
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                  <select
                    value={selectedProperty}
                    onChange={(e) => setSelectedProperty(e.target.value)}
                    disabled={loading || properties.length === 0}
                    className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {properties.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Month</label>
                  <select
                    value={selectedMonth}
                    onChange={(e) => setSelectedMonth(Number(e.target.value))}
                    className="block w-full sm:w-auto min-w-[140px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {MONTHS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>

                {selectedMonth !== 0 && (
                  <div className="flex flex-col sm:items-end">
                    <label className="text-xs font-medium text-gray-700 mb-1">Year</label>
                    <input
                      type="number"
                      value={selectedYear}
                      onChange={(e) => setSelectedYear(Number(e.target.value))}
                      className="block w-full sm:w-auto min-w-[90px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {selectedProperty && (
              <RevenueSummary
                propertyId={selectedProperty}
                month={selectedMonth === 0 ? undefined : selectedMonth}
                year={selectedMonth === 0 ? undefined : selectedYear}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;