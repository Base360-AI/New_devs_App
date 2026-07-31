import React, { useEffect, useMemo, useState } from "react";
import { useAuth } from "../contexts/AuthContext.new";
import { RevenueSummary } from "./RevenueSummary";

const ALL_PROPERTIES = [
  { id: "prop-001", name: "Beach House Alpha", tenant_id: "tenant-a" },
  { id: "prop-002", name: "City Apartment Downtown", tenant_id: "tenant-a" },
  { id: "prop-003", name: "Country Villa Estate", tenant_id: "tenant-a" },
  { id: "prop-001", name: "Mountain Lodge Beta", tenant_id: "tenant-b" },
  { id: "prop-004", name: "Lakeside Cottage", tenant_id: "tenant-b" },
  { id: "prop-005", name: "Urban Loft Modern", tenant_id: "tenant-b" },
];

function resolveTenantId(
  user: {
    tenant_id?: string;
    app_metadata?: Record<string, any>;
    user_metadata?: Record<string, any>;
  } | null,
): string | null {
  if (!user) return null;
  return (
    user.tenant_id ||
    user.app_metadata?.tenant_id ||
    user.user_metadata?.tenant_id ||
    null
  );
}

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const tenantId = resolveTenantId(user);

  const properties = useMemo(
    () => (tenantId ? ALL_PROPERTIES.filter((p) => p.tenant_id === tenantId) : []),
    [tenantId],
  );

  const [selectedProperty, setSelectedProperty] = useState(properties[0]?.id ?? "");

  useEffect(() => {
    if (properties.length === 0) {
      setSelectedProperty("");
      return;
    }
    if (!properties.some((p) => p.id === selectedProperty)) {
      setSelectedProperty(properties[0].id);
    }
  }, [properties, selectedProperty]);

  const selectedMeta = properties.find((p) => p.id === selectedProperty) ?? properties[0];

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
                {selectedMeta && (
                  <p className="text-sm text-gray-500 mt-1">
                    Viewing: <span className="font-medium text-gray-800">{selectedMeta.name}</span>
                  </p>
                )}
              </div>

              <div className="flex flex-col sm:items-end">
                <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  value={selectedProperty}
                  onChange={(e) => setSelectedProperty(e.target.value)}
                  disabled={properties.length === 0}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                >
                  {properties.map((property) => (
                    <option key={`${property.tenant_id}-${property.id}`} value={property.id}>
                      {property.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {selectedProperty ? (
              <RevenueSummary propertyId={selectedProperty} month={3} year={2024} />
            ) : (
              <p className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-md p-3">
                No properties available for this tenant.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
