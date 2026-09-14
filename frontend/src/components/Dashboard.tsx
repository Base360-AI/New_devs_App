import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";
import { useAuth } from "../contexts/AuthContext.new";

const DashboardContent: React.FC = () => {
  const [properties, setProperties] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  // The supplied reservations are from March 2024.
  const [period, setPeriod] = useState('2024-03');
  const [annual, setAnnual] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [year, month] = period.split('-').map(Number);

  useEffect(() => {
    let active = true;
    SecureAPI.getDashboardProperties()
      .then(rows => {
        if (active) {
          setProperties(rows);
          setSelectedProperty(rows[0]?.id || '');
        }
      })
      .catch(() => { if (active) setError('Failed to load properties'); })
      .finally(() => { if (active) setLoading(false); });
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
                  {annual ? 'Annual' : 'Monthly'} performance insights for your properties
                </p>
              </div>
              
              {/* Property Selector */}
              <div className="flex flex-col sm:items-end">
                <label htmlFor="revenue-property" className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  id="revenue-property"
                  disabled={loading || properties.length === 0}
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
                <label htmlFor="revenue-period" className="text-xs font-medium text-gray-700 mt-3 mb-1">Reporting month</label>
                <input id="revenue-period" type="month" min="0002-01" max="9998-12"
                  value={period} onChange={e => setPeriod(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-md text-sm" />
                <label className="text-sm text-gray-700 mt-2">
                  <input type="checkbox" checked={annual} onChange={e => setAnnual(e.target.checked)} className="mr-2" />
                  Show full year{year ? ` (${year})` : ''}
                </label>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {loading && <p role="status">Loading properties…</p>}
            {error && <p role="alert" className="text-red-600">{error}</p>}
            {!loading && !error && !properties.length && <p>No properties available.</p>}
            {!period && <p>Select a reporting month.</p>}
            {selectedProperty && year >= 2 && year <= 9998 && month >= 1 && month <= 12 && (
              <RevenueSummary key={`${selectedProperty}:${period}:${annual}`}
                propertyId={selectedProperty} year={year} month={annual ? undefined : month} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default function Dashboard() {
  const { user } = useAuth();
  return <DashboardContent key={`${user?.id}:${user?.tenant_id}`} />;
}
