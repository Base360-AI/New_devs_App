import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";
import { useAuth } from "../contexts/AuthContext.new";

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const [properties, setProperties] = useState<{ id: string; name: string }[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertyError, setPropertyError] = useState('');
  const [period, setPeriod] = useState(() => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
  });
  const [year, month] = period.split('-').map(Number);

  useEffect(() => {
    let cancelled = false;
    setProperties([]);
    setSelectedProperty('');
    setPropertyError('');
    SecureAPI.getDashboardProperties().then((items) => {
      if (!cancelled) {
        setProperties(items);
        setSelectedProperty(items[0]?.id || '');
      }
    }).catch(() => {
      if (!cancelled) setPropertyError('Failed to load properties');
    });
    return () => { cancelled = true; };
  }, [user?.tenant_id]);

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
                <label htmlFor="revenue-month" className="text-xs font-medium text-gray-700 mb-1">Month</label>
                <input
                  id="revenue-month"
                  type="month"
                  min="0001-01"
                  max="9998-12"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                  className="border border-gray-300 rounded-md px-3 py-2 mb-3"
                />
                <label htmlFor="revenue-property" className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  id="revenue-property"
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
            {propertyError && <p className="text-red-500">{propertyError}</p>}
            {selectedProperty && month >= 1 && month <= 12 && year >= 1 && year <= 9998 && (
              <RevenueSummary key={`${user?.tenant_id}:${selectedProperty}:${period}`} propertyId={selectedProperty} month={month} year={year} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
