import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";
import { getApiErrorDetail } from "../utils/errorMessages";

interface Property {
  id: string;
  name: string;
  timezone: string;
}

// Month names from the browser locale; built in UTC so no month is skipped or repeated
const MONTHS = Array.from({ length: 12 }, (_, i) => ({
  value: i + 1,
  label: new Date(Date.UTC(2000, i, 1)).toLocaleDateString(undefined, { month: 'long', timeZone: 'UTC' })
}));

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - i);

const selectClassName = "block w-full sm:w-auto px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm disabled:bg-gray-100 disabled:text-gray-400";

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  // 0 means all time; otherwise a 1-12 month paired with selectedYear
  const [selectedMonth, setSelectedMonth] = useState(0);
  const [selectedYear, setSelectedYear] = useState(CURRENT_YEAR);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const fetchProperties = async () => {
      try {
        // [LEAK] Replaces the hardcoded list of all 5 properties with the logged-in tenant's own list from the API
        const result = await SecureAPI.getDashboardProperties();
        if (cancelled) return;
        setProperties(result);
        setSelectedProperty(result[0]?.id ?? '');
      } catch (err) {
        console.error(err);
        if (!cancelled) setError(getApiErrorDetail(err, 'Failed to load properties'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchProperties();
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

              {properties.length > 0 && (
                <div className="flex flex-col sm:flex-row gap-3">
                  {/* Property Selector */}
                  <div className="flex flex-col">
                    <label htmlFor="property-select" className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                    <select
                      id="property-select"
                      value={selectedProperty}
                      onChange={(e) => setSelectedProperty(e.target.value)}
                      className={`${selectClassName} min-w-[200px]`}
                    >
                      {properties.map((property) => (
                        <option key={property.id} value={property.id}>
                          {property.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Period Selector */}
                  <div className="flex flex-col">
                    <label htmlFor="month-select" className="text-xs font-medium text-gray-700 mb-1">Month</label>
                    <select
                      id="month-select"
                      value={selectedMonth}
                      onChange={(e) => setSelectedMonth(Number(e.target.value))}
                      className={selectClassName}
                    >
                      <option value={0}>All time</option>
                      {MONTHS.map((month) => (
                        <option key={month.value} value={month.value}>
                          {month.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col">
                    <label htmlFor="year-select" className="text-xs font-medium text-gray-700 mb-1">Year</label>
                    <select
                      id="year-select"
                      value={selectedYear}
                      onChange={(e) => setSelectedYear(Number(e.target.value))}
                      disabled={selectedMonth === 0}
                      className={selectClassName}
                    >
                      {YEARS.map((year) => (
                        <option key={year} value={year}>
                          {year}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-6">
            {loading ? (
              <div className="h-40 bg-gray-50 rounded-xl animate-pulse" />
            ) : error ? (
              <div className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>
            ) : properties.length === 0 ? (
              <div className="p-4 text-gray-500 bg-gray-50 rounded-lg">No properties found for your account.</div>
            ) : (
              <RevenueSummary
                propertyId={selectedProperty}
                month={selectedMonth || undefined}
                year={selectedMonth ? selectedYear : undefined}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
