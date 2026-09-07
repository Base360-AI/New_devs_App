import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";
import { useAuth } from "../contexts/AuthContext.new";

interface Property {
  id: string;
  name: string;
  timezone?: string;
}

const FALLBACK_TENANT_PROPERTIES: Record<string, Property[]> = {
  'tenant-a': [
    { id: 'prop-001', name: 'Beach House Alpha' },
    { id: 'prop-002', name: 'City Apartment Downtown' },
    { id: 'prop-003', name: 'Country Villa Estate' }
  ],
  'tenant-b': [
    { id: 'prop-001', name: 'Mountain Lodge Beta' },
    { id: 'prop-004', name: 'Lakeside Cottage' },
    { id: 'prop-005', name: 'Urban Loft Modern' }
  ]
};

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const tenantId = user?.tenant_id || 'tenant-a';

  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState<string>('');
  const [period, setPeriod] = useState<string>(''); // '' = all time, 'YYYY-MM' for specific month

  useEffect(() => {
    let active = true;
    SecureAPI.getDashboardProperties()
      .then((list: Property[]) => {
        if (!active) return;
        if (list && list.length > 0) {
          setProperties(list);
          setSelectedProperty(prev => list.some(p => p.id === prev) ? prev : list[0].id);
        } else {
          const fallback = FALLBACK_TENANT_PROPERTIES[tenantId] || FALLBACK_TENANT_PROPERTIES['tenant-a'];
          setProperties(fallback);
          setSelectedProperty(prev => fallback.some(p => p.id === prev) ? prev : fallback[0].id);
        }
      })
      .catch((err) => {
        console.warn('[Dashboard] Failed to fetch properties from API, using fallback:', err);
        if (!active) return;
        const fallback = FALLBACK_TENANT_PROPERTIES[tenantId] || FALLBACK_TENANT_PROPERTIES['tenant-a'];
        setProperties(fallback);
        setSelectedProperty(prev => fallback.some(p => p.id === prev) ? prev : fallback[0].id);
      });

    return () => { active = false; };
  }, [tenantId]);


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
                {/* Dynamic Property Selector */}
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                  <select
                    value={selectedProperty}
                    onChange={(e) => setSelectedProperty(e.target.value)}
                    disabled={properties.length === 0}
                    className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {properties.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name} {property.timezone ? `(${property.timezone})` : ''}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Period</label>
                  <div className="flex gap-2">
                    <input
                      type="month"
                      value={period}
                      onChange={(e) => setPeriod(e.target.value)}
                      className="block px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                    />
                    {period && (
                      <button
                        type="button"
                        onClick={() => setPeriod('')}
                        className="px-3 py-2 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                      >
                        All time
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {selectedProperty && (
              <RevenueSummary propertyId={selectedProperty} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
