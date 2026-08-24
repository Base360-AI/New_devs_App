import React, { useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { useAppContext } from "../contexts/AppContext";

interface PropertyOption {
  id: string;
  name: string;
}

const PROPERTIES_BY_TENANT: Record<string, PropertyOption[]> = {
  'tenant-a': [
    { id: 'prop-001', name: 'Beach House Alpha' },
    { id: 'prop-002', name: 'City Apartment Downtown' },
    { id: 'prop-003', name: 'Country Villa Estate' },
  ],
  'tenant-b': [
    { id: 'prop-001', name: 'Mountain Lodge Beta' },
    { id: 'prop-004', name: 'Lakeside Cottage' },
    { id: 'prop-005', name: 'Urban Loft Modern' },
  ],
};

const REPORTING_YEAR = 2024;
const REPORTING_MONTH = 3;

const Dashboard: React.FC = () => {
  const { user } = useAppContext();
  const properties = PROPERTIES_BY_TENANT[user?.tenant_id ?? ''] ?? [];
  const [selectedProperty, setSelectedProperty] = useState('prop-001');

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
                  March 2024 performance insights for your properties
                </p>
              </div>
              
              {/* Property Selector */}
              <div className="flex flex-col sm:items-end">
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
            <RevenueSummary
              propertyId={selectedProperty}
              year={REPORTING_YEAR}
              month={REPORTING_MONTH}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
