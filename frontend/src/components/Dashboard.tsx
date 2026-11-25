import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from '../lib/secureApi';
import { property } from "../types/profile";


const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [properties, setProperties] = useState<property[]>([]);  
  const [selectedProperty, setSelectedProperty] = useState('prop-001');
  const [error, setError] = useState('');
  
  useEffect(() => {
    const fetchRevenue = async () => {
      setLoading(true);
      try {
        // Use SecureAPI to handle authentication automatically
        // We pass the simulatedTenant option which SecureAPI will attach as a header
        const response = await SecureAPI.getTenantProperties();
        setProperties(response.properties);
      } catch (err) {
        setError('Failed to load revenue data');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchRevenue();
  }, []);
  
  if (loading) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-100 rounded w-1/4"></div>
          <div className="h-8 bg-gray-100 rounded w-1/2"></div>
          <div className="flex gap-4 pt-4">
            <div className="h-12 bg-gray-100 rounded flex-1"></div>
            <div className="h-12 bg-gray-100 rounded flex-1"></div>
          </div>
        </div>
      </div>
    );
  }
  if (error) return <div className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>;

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
                  {properties.map((property) => (
                    <option key={property.property_id} value={property.property_id}>
                      {property.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <RevenueSummary propertyId={selectedProperty} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
