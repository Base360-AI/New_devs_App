import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface RevenueData {
    property_id: string;
    total_revenue: string;
    currency: string;
    reservations_count: number;
    month: string;
    timezone: string;
}

interface RevenueSummaryProps {
    propertyId?: string;
    month?: string;
    showRaw?: boolean;
}

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId = 'prop-001', month, showRaw }) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let active = true;
        setLoading(true);
        SecureAPI.getDashboardSummary(propertyId, { month, timestamp: Date.now() })
            .then((response) => { if (active) { setData(response); setError(''); } })
            .catch((err) => {
                console.error(err);
                if (active) setError('Failed to load revenue data. Please try again.');
            })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, [propertyId, month]);

    if (loading) return <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">Loading revenue…</div>;
    if (error) return <div role="alert" className="p-4 text-red-700 bg-red-50 rounded-lg">{error}</div>;
    if (!data) return null;

    const total = Number(data.total_revenue);
    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            {showRaw && <pre className="p-3 bg-gray-50 text-xs border-b overflow-auto">{JSON.stringify(data, null, 2)}</pre>}
            <div className="p-6">
                <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Total Revenue</h2>
                <p className="text-3xl font-bold text-gray-900 mt-1">
                    {data.currency} {total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </p>
                <p className="text-xs text-gray-500 mt-1">{data.month} · {data.timezone}</p>
                <div className="grid grid-cols-2 gap-4 pt-4 mt-4 border-t border-gray-100">
                    <div><p className="text-xs text-gray-500 font-medium uppercase">Property ID</p><p className="text-sm font-semibold font-mono mt-1">{data.property_id}</p></div>
                    <div><p className="text-xs text-gray-500 font-medium uppercase">Reservations</p><p className="text-sm font-semibold mt-1">{data.reservations_count} bookings</p></div>
                </div>
            </div>
        </div>
    );
};
