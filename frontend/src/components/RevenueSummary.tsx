import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface RevenueData {
    property_id: string;
    // Sent as a decimal string from the backend (e.g. "2250.000") so we don't
    // lose sub-cent precision in transport or in JS number representation.
    total_revenue: string;
    currency: string;
    reservations_count: number;
    month: number;
    year: number;
}

// Round a decimal string to 2 decimal places using only integer math, so we
// never round-trip the value through a binary float.
const formatRevenue = (value: string): string => {
    const trimmed = (value ?? '').trim();
    if (!trimmed) return '0.00';

    const negative = trimmed.startsWith('-');
    const abs = negative ? trimmed.slice(1) : trimmed;

    const [intRaw = '0', decRaw = ''] = abs.split('.');
    const intPart = intRaw.replace(/^0+(?=\d)/, '') || '0';
    const dec3 = (decRaw + '000').slice(0, 3);

    let cents = parseInt(dec3.slice(0, 2), 10);
    if (parseInt(dec3[2], 10) >= 5) cents += 1;

    let wholeStr = intPart;
    if (cents >= 100) {
        cents = 0;
        wholeStr = (BigInt(intPart) + 1n).toString();
    }

    const wholeWithSeparators = wholeStr.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    const formatted = `${wholeWithSeparators}.${cents.toString().padStart(2, '0')}`;
    return negative ? `-${formatted}` : formatted;
};

interface RevenueSummaryProps {
    propertyId?: string;
    debugTenant?: string;
    showRaw?: boolean;
    /** Calendar month (1-12). Defaults to current month when omitted. */
    month?: number;
    /** Calendar year. Defaults to current year when omitted. */
    year?: number;
}

const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
];

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({
    propertyId = 'prop-001',
    debugTenant,
    showRaw,
    month,
    year,
}) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const activeTenant = debugTenant || 'candidate';

    useEffect(() => {
        const fetchRevenue = async () => {
            setLoading(true);
            try {
                const response = await SecureAPI.getDashboardSummary(propertyId, {
                    simulatedTenant: activeTenant,
                    timestamp: Date.now(),
                    month,
                    year,
                });
                setData(response);
            } catch (err) {
                setError('Failed to load revenue data');
                console.error(err);
            } finally {
                setLoading(false);
            }
        };

        fetchRevenue();
    }, [propertyId, activeTenant, month, year]);

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

    const displayTotal = formatRevenue(data.total_revenue);
    const periodLabel = data.month && data.year
        ? `${MONTH_NAMES[data.month - 1]} ${data.year}`
        : '';

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
                            Monthly Revenue{periodLabel && <span className="ml-2 normal-case tracking-normal text-gray-400">· {periodLabel}</span>}
                        </h2>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-3xl font-bold text-gray-900 tracking-tight">
                                {data.currency} {displayTotal}
                            </span>
                            {/* Fake trend indicator for premium feel */}
                            <span className="inline-flex items-baseline px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 md:mt-2 lg:mt-0">
                                <svg className="-ml-1 mr-0.5 h-3 w-3 flex-shrink-0 self-center text-green-500" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                                    <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
                                </svg>
                                12%
                            </span>
                        </div>
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

                {/* Precision Warning Area
                    Compares the raw decimal string from the API against the
                    rounded display value. The comparison is done on string
                    digits beyond the 2nd decimal place so we don't reintroduce
                    float math. Anything past .00 in the raw value means we
                    truncated, which is expected for NUMERIC(10,3) inputs. */}
                <div className="mt-4 h-6">
                    {showRaw && /\.\d{2}[1-9]/.test(data.total_revenue ?? '') && (
                        <div className="flex items-center text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded">
                            <svg className="h-4 w-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            Sub-cent precision present (rounded for display)
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
