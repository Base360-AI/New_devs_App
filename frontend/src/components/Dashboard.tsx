import React, { useState } from "react";
import { RevenueSummary } from "./RevenueSummary";

const PROPERTIES = [
  { id: 'prop-001', name: 'Beach House Alpha' },
  { id: 'prop-002', name: 'City Apartment Downtown' },
  { id: 'prop-003', name: 'Country Villa Estate' },
  { id: 'prop-004', name: 'Lakeside Cottage' },
  { id: 'prop-005', name: 'Urban Loft Modern' }
];

const MONTH_OPTIONS = (() => {
  const options: Array<{ value: string; label: string }> = [];
  const today = new Date();

  for (let year = 2024; year <= today.getFullYear(); year += 1) {
    const lastMonth = year === today.getFullYear() ? today.getMonth() : 11;

    for (let month = 0; month <= lastMonth; month += 1) {
      const value = `${year}-${String(month + 1).padStart(2, '0')}`;
      const label = new Intl.DateTimeFormat(undefined, {
        month: 'long',
        year: 'numeric',
        timeZone: 'UTC'
      }).format(new Date(Date.UTC(year, month, 1)));

      options.push({ value, label });
    }
  }

  return options.reverse();
})();

const Dashboard: React.FC = () => {
  const [selectedProperty, setSelectedProperty] = useState('prop-001');
  const [selectedMonth, setSelectedMonth] = useState('2024-03');
  const [selectedCurrency, setSelectedCurrency] = useState('USD');

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
              
              <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
                <div className="flex flex-col">
                  <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                  <select
                    value={selectedProperty}
                    onChange={(e) => setSelectedProperty(e.target.value)}
                    className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {PROPERTIES.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col">
                  <label className="text-xs font-medium text-gray-700 mb-1">Select Month</label>
                  <select
                    value={selectedMonth}
                    onChange={(e) => setSelectedMonth(e.target.value)}
                    className="block w-full sm:w-auto min-w-[160px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {MONTH_OPTIONS.map((month) => (
                      <option key={month.value} value={month.value}>
                        {month.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col">
                  <label className="text-xs font-medium text-gray-700 mb-1">Currency</label>
                  <select
                    value={selectedCurrency}
                    onChange={(e) => setSelectedCurrency(e.target.value)}
                    className="block w-full sm:w-auto min-w-[100px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    <option value="USD">USD</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <RevenueSummary
              propertyId={selectedProperty}
              month={selectedMonth}
              currency={selectedCurrency}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
