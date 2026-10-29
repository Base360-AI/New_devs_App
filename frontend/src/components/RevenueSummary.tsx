import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface RevenueData {
    property_id: string;
    property_name?: string;
    timezone?: string;
    year?: number;
    month?: number;
    total_revenue: string;
    currency: string;
    reservations_count: number;
}

interface RevenueSummaryProps {
    propertyId: string;
    month: number;
    year: number;
}

const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

function formatMoney(amount: string): string {
    const negative = amount.startsWith('-');
    const [whole, frac = '00'] = amount.replace('-', '').split('.');
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return `${negative ? '-' : ''}${grouped}.${frac.padEnd(2, '0').slice(0, 2)}`;
}

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId, month, year }) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;
    
        const fetchRevenue = async () => {
            setLoading(true);
            setError('');
            try {
                const response = await SecureAPI.getDashboardSummary(propertyId, { month, year });
                if (cancelled) return;
                setData(response);
            } catch (err) {
                if (cancelled) return;
                setData(null);
                setError('Failed to load revenue data');
                console.error(err);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
    
        fetchRevenue();
        return () => {
            cancelled = true;
        };
    }, [propertyId, month, year]);

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
    if (!data) return null;

    const period = `${MONTHS[(data.month || month) - 1]} ${data.year || year}`;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-300">
            <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">{period} Revenue</h2>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-3xl font-bold text-gray-900 tracking-tight">
                                {data.currency} {formatMoney(String(data.total_revenue))}
                            </span>
                        </div>
                        {data.timezone && (
                            <p className="text-xs text-gray-500 mt-2">Counted in {data.timezone}</p>
                        )}
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Property</p>
                        <p className="text-sm font-semibold text-gray-700 mt-1">{data.property_name || data.property_id}</p>
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