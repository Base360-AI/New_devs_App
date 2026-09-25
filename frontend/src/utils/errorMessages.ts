/**
 * User-friendly error message mapping and utilities
 */

export interface ErrorContext {
  operation?: string; // e.g., 'loading', 'updating', 'deleting'
  entity?: string; // e.g., 'cleaning', 'property', 'reservation'
  retryCount?: number;
  maxRetries?: number;
}

export interface UserFriendlyError {
  title: string;
  message: string;
  actionLabel?: string;
  actionType?: 'retry' | 'refresh' | 'contact_support' | 'dismiss';
  severity: 'error' | 'warning' | 'info';
  isRetryable: boolean;
}

/**
 * Maps technical errors to user-friendly messages
 */
export function mapErrorToUserFriendly(
  error: any, 
  context: ErrorContext = {}
): UserFriendlyError {
  const { operation = 'loading', entity = 'data', retryCount = 0, maxRetries = 3 } = context;
  
  // Network/Connection errors
  if (isNetworkError(error)) {
    if (retryCount >= maxRetries) {
      return {
        title: 'Connection Problem',
        message: `Unable to connect after ${maxRetries} attempts. Please check your internet connection.`,
        actionLabel: 'Try Again',
        actionType: 'retry',
        severity: 'error',
        isRetryable: true
      };
    }
    
    return {
      title: 'Connection Issue',
      message: `Having trouble connecting. Retrying in a moment...`,
      actionLabel: 'Retry Now',
      actionType: 'retry',
      severity: 'warning',
      isRetryable: true
    };
  }
  
  // Authentication errors
  if (isAuthenticationError(error)) {
    return {
      title: 'Session Expired',
      message: 'Please sign in again to continue.',
      actionLabel: 'Sign In',
      actionType: 'refresh',
      severity: 'error',
      isRetryable: false
    };
  }
  
  // Permission errors
  if (isPermissionError(error)) {
    return {
      title: 'Access Denied',
      message: `You don't have permission to perform this action on ${entity}.`,
      actionLabel: 'Contact Support',
      actionType: 'contact_support',
      severity: 'error',
      isRetryable: false
    };
  }
  
  // Server errors (5xx)
  if (isServerError(error)) {
    return {
      title: 'Server Error',
      message: `Something went wrong on our end while ${operation} ${entity}. Our team has been notified.`,
      actionLabel: 'Try Again',
      actionType: 'retry',
      severity: 'error',
      isRetryable: true
    };
  }
  
  // Rate limiting
  if (isRateLimitError(error)) {
    return {
      title: 'Too Many Requests',
      message: 'Please wait a moment before trying again.',
      actionLabel: 'Wait and Retry',
      actionType: 'retry',
      severity: 'warning',
      isRetryable: true
    };
  }
  
  // Validation errors
  if (isValidationError(error)) {
    return {
      title: 'Invalid Data',
      message: error.message || `The ${entity} data is not valid. Please check your input.`,
      actionLabel: 'Fix and Retry',
      actionType: 'dismiss',
      severity: 'warning',
      isRetryable: false
    };
  }
  
  // Not found errors
  if (isNotFoundError(error)) {
    return {
      title: 'Not Found',
      message: `The requested ${entity} could not be found. It may have been deleted.`,
      actionLabel: 'Refresh',
      actionType: 'refresh',
      severity: 'warning',
      isRetryable: false
    };
  }
  
  // Timeout errors
  if (isTimeoutError(error)) {
    return {
      title: 'Request Timeout',
      message: `${operation} ${entity} is taking longer than expected.`,
      actionLabel: 'Try Again',
      actionType: 'retry',
      severity: 'warning',
      isRetryable: true
    };
  }
  
  // Generic fallback
  return {
    title: 'Something Went Wrong',
    message: error.message || `An unexpected error occurred while ${operation} ${entity}.`,
    actionLabel: 'Try Again',
    actionType: 'retry',
    severity: 'error',
    isRetryable: true
  };
}

/**
 * Error type detection functions
 */
export function isNetworkError(error: any): boolean {
  return (
    !error?.status ||
    error?.code === 'NETWORK_ERROR' ||
    error?.name === 'NetworkError' ||
    error?.message?.includes('fetch') ||
    error?.message?.includes('network') ||
    error?.message?.toLowerCase().includes('connection')
  );
}

export function isAuthenticationError(error: any): boolean {
  return error?.status === 401 || error?.message?.includes('unauthorized');
}

export function isPermissionError(error: any): boolean {
  return error?.status === 403 || error?.message?.includes('forbidden');
}

export function isServerError(error: any): boolean {
  return error?.status >= 500 && error?.status < 600;
}

export function isRateLimitError(error: any): boolean {
  return error?.status === 429;
}

export function isValidationError(error: any): boolean {
  return (
    error?.status === 400 ||
    error?.status === 422 ||
    error?.message?.includes('validation') ||
    error?.message?.includes('invalid')
  );
}

export function isNotFoundError(error: any): boolean {
  return error?.status === 404;
}

export function isTimeoutError(error: any): boolean {
  return (
    error?.code === 'TIMEOUT' ||
    error?.name === 'TimeoutError' ||
    error?.message?.includes('timeout')
  );
}

/**
 * Extract the backend's error detail from a SecureAPI error, which is thrown
 * as "API request failed: <detail>" without an HTTP status attached
 */
export function getApiErrorDetail(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message.replace(/^API request failed:\s*/, '') : '';
  return message || fallback;
}

/**
 * Get retry delay with human-readable format
 */
export function getRetryDelayMessage(retryCount: number, baseDelay: number = 1000): string {
  const delay = baseDelay * Math.pow(2, retryCount);
  
  if (delay < 1000) {
    return `${delay}ms`;
  } else if (delay < 60000) {
    return `${Math.round(delay / 1000)}s`;
  } else {
    return `${Math.round(delay / 60000)}m`;
  }
}

/**
 * Get context-specific error messages for cleaning operations
 */
export function getCleaningErrorContext(operation: string): ErrorContext {
  const operationMap: Record<string, { operation: string; entity: string }> = {
    'fetch': { operation: 'loading', entity: 'cleaning reports' },
    'create': { operation: 'creating', entity: 'cleaning report' },
    'update': { operation: 'updating', entity: 'cleaning report' },
    'delete': { operation: 'deleting', entity: 'cleaning report' },
    'status_change': { operation: 'updating status of', entity: 'cleaning' },
    'assign_cleaner': { operation: 'assigning cleaner to', entity: 'cleaning' },
    'poll': { operation: 'refreshing', entity: 'cleaning data' }
  };
  
  return operationMap[operation] || { operation, entity: 'cleaning' };
}

/**
 * Format error for display in UI components
 */
export function formatErrorForDisplay(error: any, context: ErrorContext = {}): {
  title: string;
  message: string;
  canRetry: boolean;
  severity: 'error' | 'warning' | 'info';
} {
  const userError = mapErrorToUserFriendly(error, context);
  
  return {
    title: userError.title,
    message: userError.message,
    canRetry: userError.isRetryable,
    severity: userError.severity
  };
}

/**
 * Get appropriate toast notification settings for error
 */
export function getErrorToastConfig(error: any, context: ErrorContext = {}) {
  const userError = mapErrorToUserFriendly(error, context);
  
  return {
    title: userError.title,
    description: userError.message,
    status: userError.severity === 'error' ? 'error' : 'warning',
    duration: userError.severity === 'error' ? 0 : 5000, // Errors persist, warnings auto-dismiss
    isClosable: true
  };
}