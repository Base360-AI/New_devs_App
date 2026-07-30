import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface RevenueData {
    property_id: string;
    // Monetary values are transported as strings so no amount ever passes
    // through a JS number and picks up binary floating point error.
    total_revenue: string;
    total_revenue_exact: string;
    currency: string;
    reservations_count: number;
    period: string;
    timezone: string;
}

interface RevenueSummaryProps {
    propertyId?: string;
    month?: number;
    year?: number;
    showRaw?: boolean;
}

const formatMoney = (amount: string, currency: string) => {
    // Split on the decimal point and group the integer part by hand: the value
    // is already rounded to cents server-side and must be rendered verbatim.
    const [whole, fraction = '00'] = amount.split('.');
    const negative = whole.startsWith('-');
    const digits = negative ? whole.slice(1) : whole;
    const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return `${currency} ${negative ? '-' : ''}${grouped}.${fraction}`;
};

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId = 'prop-001', month, year, showRaw }) => {
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
                if (!cancelled) setData(response);
            } catch (err) {
                if (!cancelled) {
                    setData(null);
                    setError('Failed to load revenue data');
                }
                console.error(err);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        fetchRevenue();

        // A slower in-flight request for a previously selected property must
        // not land after a newer one and show the wrong property's revenue.
        return () => { cancelled = true; };
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

    const roundedAwayFromExact = Number(data.total_revenue_exact) !== Number(data.total_revenue);

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
                        <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
                            Total Revenue{data.period !== 'all-time' ? ` · ${data.period}` : ''}
                        </h2>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-3xl font-bold text-gray-900 tracking-tight">
                                {formatMoney(data.total_revenue, data.currency)}
                            </span>
                        </div>
                        <p className="text-xs text-gray-400 mt-1">
                            Periods are calculated in the property's local time ({data.timezone})
                        </p>
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

                {/* Sub-cent amounts are summed exactly and rounded once; surface
                    the residual so finance can reconcile against raw bookings. */}
                <div className="mt-4 h-6">
                    {roundedAwayFromExact && showRaw && (
                        <div className="flex items-center text-xs text-gray-500 bg-gray-50 px-2 py-1 rounded">
                            Exact sum {data.total_revenue_exact} rounded to {data.total_revenue}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
