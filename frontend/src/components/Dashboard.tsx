import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";
import { useAuth } from "../contexts/AuthContext.new";

interface Property {
  id: string;
  name: string;
  timezone: string;
}

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertiesLoading, setPropertiesLoading] = useState(true);
  const [propertiesError, setPropertiesError] = useState('');
  const [periodType, setPeriodType] = useState<'month' | 'year'>('month');
  const [year, setYear] = useState(2024);
  const [month, setMonth] = useState(3);

  useEffect(() => {
    let active = true;

    const loadProperties = async () => {
      setPropertiesLoading(true);
      setPropertiesError('');
      setProperties([]);
      setSelectedProperty('');
      try {
        const result = await SecureAPI.getProperties({ page_size: 1000 });
        if (active) {
          const items = result.data as Property[];
          setProperties(items);
          setSelectedProperty(items[0]?.id || '');
        }
      } catch (error) {
        if (active) {
          setPropertiesError('Failed to load properties');
          console.error(error);
        }
      } finally {
        if (active) {
          setPropertiesLoading(false);
        }
      }
    };

    loadProperties();
    return () => {
      active = false;
    };
  }, [user?.id, user?.tenant_id]);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col lg:flex-row lg:justify-between lg:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">Revenue Overview</h2>
                <p className="text-sm lg:text-base text-gray-600">
                  {periodType === 'month' ? 'Monthly' : 'Annual'} performance insights for your properties
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <div>
                  <label htmlFor="period-type" className="block text-xs font-medium text-gray-700 mb-1">Period</label>
                  <select
                    id="period-type"
                    value={periodType}
                    onChange={(event) => setPeriodType(event.target.value as 'month' | 'year')}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm"
                  >
                    <option value="month">Monthly</option>
                    <option value="year">Annual</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="reporting-year" className="block text-xs font-medium text-gray-700 mb-1">Year</label>
                  <input
                    id="reporting-year"
                    type="number"
                    min={1900}
                    max={9998}
                    value={year}
                    onChange={(event) => {
                      if (Number.isFinite(event.target.valueAsNumber)) {
                        setYear(event.target.valueAsNumber);
                      }
                    }}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm"
                  />
                </div>

                {periodType === 'month' && (
                  <div>
                    <label htmlFor="reporting-month" className="block text-xs font-medium text-gray-700 mb-1">Month</label>
                    <select
                      id="reporting-month"
                      value={month}
                      onChange={(event) => setMonth(Number(event.target.value))}
                      className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm"
                    >
                      {Array.from({ length: 12 }, (_, index) => index + 1).map((value) => (
                        <option key={value} value={value}>{value}</option>
                      ))}
                    </select>
                  </div>
                )}

                <div>
                  <label htmlFor="property-selector" className="block text-xs font-medium text-gray-700 mb-1">Property</label>
                  <select
                    id="property-selector"
                    value={selectedProperty}
                    onChange={(event) => setSelectedProperty(event.target.value)}
                    disabled={propertiesLoading || properties.length === 0}
                    className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm disabled:bg-gray-100"
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

          {propertiesLoading && <p className="text-sm text-gray-500">Loading properties...</p>}
          {propertiesError && <p className="text-sm text-red-600">{propertiesError}</p>}
          {!propertiesLoading && !propertiesError && properties.length === 0 && (
            <p className="text-sm text-gray-500">No properties are available for this account.</p>
          )}
          {selectedProperty && (
            <RevenueSummary
              key={`${user?.id || 'unknown'}:${user?.tenant_id || 'unknown'}`}
              propertyId={selectedProperty}
              year={year}
              month={periodType === 'month' ? month : undefined}
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
