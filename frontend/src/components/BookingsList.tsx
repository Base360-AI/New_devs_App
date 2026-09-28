import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface Booking {
    id: string;
    check_in: string;
    check_out: string;
    amount: string;
    currency: string;
}

interface BookingsListProps {
    propertyId: string;
    month?: string; // "YYYY-MM"
}

export const BookingsList: React.FC<BookingsListProps> = ({ propertyId, month }) => {
    const [bookings, setBookings] = useState<Booking[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        setLoading(true);
        setError('');
        SecureAPI.getDashboardReservations(propertyId, {
            year: month ? Number(month.split('-')[0]) : undefined,
            month: month ? Number(month.split('-')[1]) : undefined
        })
            .then((res) => setBookings(res.reservations))
            .catch((err) => {
                setError('Failed to load bookings');
                console.error(err);
            })
            .finally(() => setLoading(false));
    }, [propertyId, month]);

    if (loading) return <div className="p-4 text-sm text-gray-400">Loading bookings...</div>;
    if (error) return <div className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>;

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
                <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
                    Bookings ({bookings.length})
                </h2>
            </div>

            {bookings.length === 0 ? (
                <p className="px-6 py-8 text-sm text-gray-400 text-center">No bookings for this period.</p>
            ) : (
                <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                        <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wider">
                            <tr>
                                <th className="px-6 py-3 text-left font-medium">Booking</th>
                                <th className="px-6 py-3 text-left font-medium">Check-in</th>
                                <th className="px-6 py-3 text-left font-medium">Check-out</th>
                                <th className="px-6 py-3 text-right font-medium">Amount</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                            {bookings.map((b) => (
                                <tr key={b.id}>
                                    <td className="px-6 py-3 font-mono text-gray-700">{b.id}</td>
                                    <td className="px-6 py-3 text-gray-700 whitespace-nowrap">{b.check_in}</td>
                                    <td className="px-6 py-3 text-gray-700 whitespace-nowrap">{b.check_out}</td>
                                    <td className="px-6 py-3 text-right text-gray-900 whitespace-nowrap">
                                        {b.currency} {Number(b.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 3 })}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};
