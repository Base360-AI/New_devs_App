import React, { useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { useAuth } from "../contexts/AuthContext.new";

const PROPERTIES = [
  { id: 'prop-001', tenant: 'tenant-a', name: 'Beach House Alpha' },
  { id: 'prop-001', tenant: 'tenant-b', name: 'Mountain Lodge Beta' },
  { id: 'prop-002', tenant: 'tenant-a', name: 'City Apartment Downtown' },
  { id: 'prop-003', tenant: 'tenant-a', name: 'Country Villa Estate' },
  { id: 'prop-004', tenant: 'tenant-b', name: 'Lakeside Cottage' },
  { id: 'prop-005', tenant: 'tenant-b', name: 'Urban Loft Modern' }
];

const EMAIL_TENANT_MAP: Record<string, 'tenant-a' | 'tenant-b'> = {
  'sunset@propertyflow.com': 'tenant-a',
  'ocean@propertyflow.com': 'tenant-b',
  'candidate@propertyflow.com': 'tenant-a'
};

type DashboardTenant = 'tenant-a' | 'tenant-b';

function resolveDashboardTenant(user: any): DashboardTenant | null {
  const directTenant = user?.tenant_id || user?.user_metadata?.tenant_id || user?.app_metadata?.tenant_id;
  if (directTenant === 'tenant-a' || directTenant === 'tenant-b') {
    return directTenant;
  }

  const email = (user?.email || '').toLowerCase();
  return EMAIL_TENANT_MAP[email] || null;
}

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const loggedInTenant = resolveDashboardTenant(user);
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
                  Monthly performance insights for your properties
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
                  {PROPERTIES.filter((property) => loggedInTenant && property.tenant === loggedInTenant).map((property) => (
                    <option key={`${property.tenant}:${property.id}`} value={property.id}>
                      {property.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <RevenueSummary propertyId={selectedProperty} tenantId={loggedInTenant} debugTenant={loggedInTenant || undefined} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
