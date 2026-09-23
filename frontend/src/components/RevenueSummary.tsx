import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';
import { useAuth } from '../contexts/AuthContext.new';

interface RevenueData {
    property_id: string;
    total_revenue: string | null;
    currency: string | null;
    totals: { currency: string; total: string; count: number }[];
    reservations_count: number;
}

interface RevenueSummaryProps {
    propertyId?: string;
    debugTenant?: string;
    showRaw?: boolean;
    month?: number;
    year?: number;
}

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({
    propertyId = 'prop-001',
    debugTenant,
    showRaw,
    month = 3,
    year = 2024
}) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const activeTenant = debugTenant || 'candidate';
    const { user } = useAuth();

    useEffect(() => {
        let cancelled = false;
        const fetchRevenue = async () => {
            setLoading(true);
            setError('');
            setData(null);

            try {
                // SecureAPI handles authentication automatically.
                const response = await SecureAPI.getDashboardSummary(propertyId, {
                    month,
                    year,
                    timestamp: Date.now()
                });

                if (!cancelled) setData(response);
            } catch (err) {
                if (!cancelled) setError('Failed to load revenue data');
                console.error(err);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        fetchRevenue();
        return () => { cancelled = true; };
    }, [propertyId, activeTenant, month, year, user?.id]);

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

    if (error) {
        return (
            <div className="p-4 text-red-500 bg-red-50 rounded-lg">
                {error}
            </div>
        );
    }

    if (!data) return null;

    // Keep the monetary value as the exact decimal string returned by
    // the backend instead of converting it to a JavaScript Number.


    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-300">

            {showRaw && (
                <div className="p-3 bg-gray-50 text-xs font-mono border-b border-gray-100 overflow-auto max-h-32">
                    <strong className="block mb-1 text-gray-500 uppercase tracking-wider text-[10px]">
                        Raw API Response
                    </strong>

                    <pre className="text-gray-700">
                        {JSON.stringify(data, null, 2)}
                    </pre>
                </div>
            )}

            <div className="p-6">

                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
                            Total Revenue
                        </h2>

                        <div className="flex items-baseline gap-2 mt-1">

                            <span className="text-3xl font-bold text-gray-900 tracking-tight">
                                {data.totals.length === 0 ? 'No reservations this month' : data.totals.map(total => (
                                    <span className="block" key={total.currency}>{total.currency} {total.total}</span>
                                ))}
                            </span>

                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">

                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
                            Property ID
                        </p>

                        <p className="text-sm font-semibold text-gray-700 font-mono mt-1">
                            {data.property_id}
                        </p>
                    </div>

                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">
                            Reservations
                        </p>

                        <p className="text-sm font-semibold text-gray-700 mt-1">
                            {data.reservations_count}{' '}
                            <span className="font-normal text-gray-400">
                                bookings
                            </span>
                        </p>
                    </div>

                </div>

            </div>
        </div>
    );
};
