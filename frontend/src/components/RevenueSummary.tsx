import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';
import { getApiErrorDetail } from '../utils/errorMessages';

interface RevenueData {
    property_id: string;
    total_revenue: string; // Decimal string already rounded to cents by the API
    month: number | null;
    year: number | null;
    currency: string;
    reservations_count: number;
}

interface RevenueSummaryProps {
    propertyId: string;
    month?: number; // 1-12; omit together with year for all-time figures
    year?: number;
    showRaw?: boolean;
}

// [TZ] Label built in UTC so the viewer's own timezone can't shift "March" into "February"
const formatPeriod = (month: number | null, year: number | null) => {
    if (!month || !year) return 'All time';
    return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString(undefined, {
        month: 'long',
        year: 'numeric',
        timeZone: 'UTC'
    });
};

// [CENTS] Replaces Math.round(total * 100) / 100: the API already rounded, so only format here, never re-round a float
const formatMoney = (amount: string, currency: string) => {
    const value = Number(amount);
    try {
        return value.toLocaleString(undefined, {
            style: 'currency',
            currency,
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    } catch {
        // Unknown currency code: fall back to code + plain number
        return `${currency} ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
};

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId, month, year, showRaw }) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        // Ignore responses for a property or period the user has already switched away from
        let cancelled = false;

        const fetchRevenue = async () => {
            setLoading(true);
            setError('');
            try {
                // [LEAK] Removed the client-sent X-Simulated-Tenant header: the tenant now comes only from the auth token
                const response = await SecureAPI.getDashboardSummary(propertyId, {
                    month,
                    year,
                    timestamp: Date.now()
                });
                if (!cancelled) setData(response);
            } catch (err) {
                console.error(err);
                if (!cancelled) {
                    setData(null);
                    setError(getApiErrorDetail(err, 'Failed to load revenue data'));
                }
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

    const displayTotal = formatMoney(data.total_revenue, data.currency);

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-300">
            {showRaw && (
                <div className="p-3 bg-gray-50 text-xs font-mono border-b border-gray-100 overflow-auto max-h-32">
                    <strong className="block mb-1 text-gray-500 uppercase tracking-wider text-[10px]">Raw API Response</strong>
                    <pre className="text-gray-700">{JSON.stringify(data, null, 2)}</pre>
                </div>
            )}

            <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Total Revenue</h2>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-3xl font-bold text-gray-900 tracking-tight">
                                {displayTotal}
                            </span>
                        </div>
                        <p className="text-sm text-gray-500 mt-1">{formatPeriod(data.month, data.year)}</p>
                    </div>
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
