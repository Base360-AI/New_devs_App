import React, { useState, useEffect } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";


// Bug 1: Both customers have a shared list of properties?
// Looks suspicious:D
// UPD: yes, this it a bug
// INSERT INTO properties (id, tenant_id, name, timezone) VALUES
//     ('prop-001', 'tenant-a', 'Beach House Alpha', 'Europe/Paris'),
//     ('prop-001', 'tenant-b', 'Mountain Lodge Beta', 'America/New_York'),
//     ('prop-002', 'tenant-a', 'City Apartment Downtown', 'Europe/Paris'),
//     ('prop-003', 'tenant-a', 'Country Villa Estate', 'Europe/Paris'),
//     ('prop-004', 'tenant-b', 'Lakeside Cottage', 'America/New_York'),
//     ('prop-005', 'tenant-b', 'Urban Loft Modern', 'America/New_York');

// const PROPERTIES = [
//   { id: 'prop-001', name: 'Beach House Alpha' },
//   { id: 'prop-002', name: 'City Apartment Downtown' },
//   { id: 'prop-003', name: 'Country Villa Estate' },
//   { id: 'prop-004', name: 'Lakeside Cottage' },
//   { id: 'prop-005', name: 'Urban Loft Modern' }
// ];

interface Property {
  id: string;
  name: string;
}

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [loadingProperties, setLoadingProperties] = useState(true);

  useEffect(() => {
    const fetchProperties = async () => {
      try {
        // I haven't found an endpoint to get a properties list, so I created a new endpoint
        // Sorry if it's actually available:(
        // Yeah, react-query is in package.json, but I'm not sure if I have enough time to use it
        const data = await SecureAPI.getDashboardProperties();
        setProperties(data);
        if (data.length > 0) {
          setSelectedProperty(data[0].id);
        }
      } catch (err) {
        console.error('Failed to load properties', err);
      } finally {
        setLoadingProperties(false);
      }
    };
    fetchProperties();
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
                <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                <select
                  value={selectedProperty}
                  onChange={(e) => setSelectedProperty(e.target.value)}
                  disabled={loadingProperties}
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                >
                  {loadingProperties && <option>Loading...</option>}
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
            {selectedProperty && <RevenueSummary propertyId={selectedProperty} />}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
