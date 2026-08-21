import React, { useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { useAuth } from "../contexts/AuthContext.new";

type PropertyOption = { id: string; name: string };

const PROPERTIES_BY_TENANT: Record<string, PropertyOption[]> = {
  "tenant-a": [
    { id: "prop-001", name: "Beach House Alpha" },
    { id: "prop-002", name: "City Apartment Downtown" },
    { id: "prop-003", name: "Country Villa Estate" },
  ],
  "tenant-b": [
    { id: "prop-001", name: "Mountain Lodge Beta" },
    { id: "prop-004", name: "Lakeside Cottage" },
    { id: "prop-005", name: "Urban Loft Modern" },
  ],
};

function listingsForTenant(tenantId: string | undefined): PropertyOption[] {
  if (!tenantId) return [];
  return PROPERTIES_BY_TENANT[tenantId] ?? [];
}

function activeListingId(listings: PropertyOption[], selectedId: string): string {
  const stillInTenant = listings.some((listing) => listing.id === selectedId);
  if (stillInTenant) return selectedId;
  return listings[0]?.id ?? "";
}

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const [selectedId, setSelectedId] = useState("");

  const properties = listingsForTenant(user?.tenant_id);
  const activePropertyId = activeListingId(properties, selectedId);

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
                  Monthly performance insights for your properties (March 2024)
                </p>
              </div>
              
              {/* Property Selector */}
              <div className="flex flex-col sm:items-end">
                <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  value={activePropertyId}
                  onChange={(e) => setSelectedId(e.target.value)}
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
            {activePropertyId ? (
              <RevenueSummary propertyId={activePropertyId} month={3} year={2024} />
            ) : (
              <p className="text-sm text-gray-500">No properties for this account.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
