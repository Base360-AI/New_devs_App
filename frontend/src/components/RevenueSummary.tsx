import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface RevenueData {
    property_id: string;
    total_revenue: string;
    currency: string;
    reservations_count: number;
}

interface RevenueSummaryProps { propertyId: string; month: string; }

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId, month }) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let active = true;
        const fetchRevenue = async () => {
            setLoading(true);
            setError('');
            try {
                const [year, monthNumber] = month.split('-').map(Number);
                const response = await SecureAPI.getDashboardSummary(propertyId, monthNumber, year);
                if (active) setData(response);
            } catch (err) {
                if (active) setError('Failed to load revenue data');
                console.error(err);
            } finally {
                if (active) setLoading(false);
            }
        };

        fetchRevenue();
        return () => { active = false; };
    }, [propertyId, month]);

    if (loading) return <div className="bg-white p-6 rounded-xl border border-gray-200">Loading revenue...</div>;
    if (error) return <div className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>;
    if (!data) return null;

    const displayTotal = Number(data.total_revenue);

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="p-6">
                <div className="mb-6">
                    <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Total Revenue</h2>
                    <span className="text-3xl font-bold text-gray-900 tracking-tight">
                        {data.currency} {displayTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                </div>
                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Property ID</p>
                        <p className="text-sm font-semibold text-gray-700 font-mono mt-1">{data.property_id}</p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Reservations</p>
                        <p className="text-sm font-semibold text-gray-700 mt-1">{data.reservations_count} <span className="font-normal text-gray-400">bookings</span></p>
                    </div>
                </div>
            </div>
        </div>
    );
};
