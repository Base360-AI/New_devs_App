import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

type DashboardProperty = { id: string; name: string; latest_month: string | null };

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<DashboardProperty[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [selectedMonth, setSelectedMonth] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    SecureAPI.getDashboardProperties()
      .then((items) => {
        if (!active) return;
        setProperties(items);
        setSelectedProperty(items[0]?.id || '');
        setSelectedMonth(items.map((item) => item.latest_month || '').sort().pop() || new Date().toISOString().slice(0, 7));
      })
      .catch(() => { if (active) setError('Failed to load properties'); });
    return () => { active = false; };
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
              
              <div className="flex flex-col sm:flex-row sm:items-end gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-700" htmlFor="dashboard-month">Month</label>
                  <input id="dashboard-month" type="month" value={selectedMonth}
                    onChange={(event) => setSelectedMonth(event.target.value)}
                    onClick={(event) => event.currentTarget.showPicker()}
                    className="block w-full sm:w-auto px-3 py-2 border border-gray-300 rounded-md text-sm" />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-700" htmlFor="dashboard-property">Select Property</label>
                  <select id="dashboard-property" value={selectedProperty}
                    onChange={(event) => setSelectedProperty(event.target.value)}
                    className="block w-full sm:w-auto min-w-[200px] pl-3 pr-10 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm">
                    {properties.map((property) => (
                      <option key={property.id} value={property.id}>{property.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {error && <div className="text-red-600">{error}</div>}
            {!error && selectedProperty && selectedMonth && (
              <RevenueSummary propertyId={selectedProperty} month={selectedMonth} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
