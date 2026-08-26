import React, { useEffect, useState } from "react";
import { SecureAPI } from "../lib/secureApi";
import { RevenueSummary } from "./RevenueSummary";

interface Property {
  id: string;
  name: string;
  timezone: string;
}

const MONTHS = Array.from({ length: 12 }, (_, index) => ({
  value: index + 1,
  label: new Intl.DateTimeFormat(undefined, { month: "long" }).format(
    new Date(2024, index, 1),
  ),
}));

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState("");
  const [month, setMonth] = useState(3);
  const [year, setYear] = useState(2024);
  const [propertiesError, setPropertiesError] = useState("");

  useEffect(() => {
    let ignore = false;

    const fetchProperties = async () => {
      try {
        const tenantProperties = await SecureAPI.getDashboardProperties();
        if (ignore) return;

        setProperties(tenantProperties);
        setSelectedProperty((current) =>
          tenantProperties.some((property) => property.id === current)
            ? current
            : (tenantProperties[0]?.id ?? ""),
        );
      } catch (error) {
        if (!ignore) setPropertiesError("Failed to load properties");
        console.error(error);
      }
    };

    fetchProperties();
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">
          Property Management Dashboard
        </h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">
                  Revenue Overview
                </h2>
                <p className="text-sm lg:text-base text-gray-600">
                  Monthly performance insights for your properties
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <div className="flex flex-col">
                  <label
                    htmlFor="dashboard-property"
                    className="text-xs font-medium text-gray-700 mb-1"
                  >
                    Property
                  </label>
                  <select
                    id="dashboard-property"
                    value={selectedProperty}
                    onChange={(event) =>
                      setSelectedProperty(event.target.value)
                    }
                    disabled={properties.length === 0}
                    className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm disabled:bg-gray-100"
                  >
                    {properties.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col">
                  <label
                    htmlFor="dashboard-month"
                    className="text-xs font-medium text-gray-700 mb-1"
                  >
                    Month
                  </label>
                  <select
                    id="dashboard-month"
                    value={month}
                    onChange={(event) => setMonth(Number(event.target.value))}
                    className="px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {MONTHS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col">
                  <label
                    htmlFor="dashboard-year"
                    className="text-xs font-medium text-gray-700 mb-1"
                  >
                    Year
                  </label>
                  <input
                    id="dashboard-year"
                    type="number"
                    min="2000"
                    max="2100"
                    value={year}
                    onChange={(event) => {
                      if (!Number.isNaN(event.target.valueAsNumber)) {
                        setYear(event.target.valueAsNumber);
                      }
                    }}
                    className="w-24 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {propertiesError && (
              <div className="p-4 text-red-500 bg-red-50 rounded-lg">
                {propertiesError}
              </div>
            )}
            {selectedProperty && (
              <RevenueSummary
                propertyId={selectedProperty}
                month={month}
                year={year}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
