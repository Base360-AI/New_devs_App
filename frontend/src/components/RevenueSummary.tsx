import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface RevenueData {
    property_id: string;
    total_revenue: string | null;
    currency: string | null;
    totals_by_currency: Record<string, string>;
    timezone: string;
    reservations_count: number;
}

interface RevenueSummaryProps {
    propertyId: string;
    year: number;
    month?: number;
    showRaw?: boolean;
}

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId, year, month, showRaw }) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let active = true;
        setLoading(true);
        setError('');
        setData(null);
        SecureAPI.getDashboardSummary(propertyId, year, month)
            .then(response => { if (active) setData(response); })
            .catch(() => { if (active) setError('Failed to load revenue data'); })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, [propertyId, year, month]);

    if (loading) return <div role="status" className="bg-white p-6 rounded-xl border border-gray-200">Loading revenue…</div>;
    if (error) return <div role="alert" className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>;
    if (!data) return null;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            {showRaw && (
                <div className="p-3 bg-gray-50 text-xs font-mono border-b border-gray-100 overflow-auto">
                    <strong>Raw API Response</strong>
                    <pre>{JSON.stringify(data, null, 2)}</pre>
                </div>
            )}
            <div className="p-6">
                <div className="mb-6">
                    <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Total Revenue</h2>
                    <div className="mt-1" aria-live="polite">
                        {Object.entries(data.totals_by_currency).map(([currency, total]) => (
                            <p key={currency} className="text-3xl font-bold text-gray-900 tracking-tight">
                                {currency} {total}
                            </p>
                        ))}
                        {data.reservations_count === 0 && (
                            <p className="text-xl text-gray-700">No revenue for this period (0.00)</p>
                        )}
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                        Check-in dates in {data.timezone}. Currencies reported separately.
                    </p>
                </div>
                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Property ID</p>
                        <p className="text-sm font-semibold text-gray-700 font-mono mt-1">{data.property_id}</p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Reservations</p>
                        <p className="text-sm font-semibold text-gray-700 mt-1">
                            {data.reservations_count} <span className="font-normal text-gray-400">bookings</span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};
