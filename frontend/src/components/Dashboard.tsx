import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
  timezone?: string;
}

const Dashboard: React.FC = () => {
  // Properties are loaded per-tenant from the API rather than hardcoded, so each
  // client sees only its own properties (and correct names). The old hardcoded
  // list showed Client A's names/ids to every tenant.
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");
    SecureAPI.getProperties()
      .then((list) => {
        if (ignore) return;
        setProperties(list);
        setSelectedProperty((prev) =>
          prev && list.some((p) => p.id === prev) ? prev : list[0]?.id ?? ""
        );
      })
      .catch((err) => {
        if (ignore) return;
        console.error(err);
        setError("Failed to load properties");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
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

              {/* Property Selector */}
              <div className="flex flex-col sm:items-end">
                <label htmlFor="property-select" className="text-xs font-medium text-gray-700 mb-1">
                  Select Property
                </label>
                <select
                  id="property-select"
                  value={selectedProperty}
                  onChange={(e) => setSelectedProperty(e.target.value)}
                  disabled={loading || properties.length === 0}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {loading && <option value="">Loading…</option>}
                  {!loading && properties.length === 0 && <option value="">No properties</option>}
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
            {error ? (
              <div className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>
            ) : !loading && properties.length === 0 ? (
              <div className="p-4 text-gray-500 bg-gray-50 rounded-lg">
                No properties found for this account.
              </div>
            ) : selectedProperty ? (
              <RevenueSummary propertyId={selectedProperty} />
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
