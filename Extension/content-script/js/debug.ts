// Debug configuration
declare global {
    var __PROD__: boolean;
}

export enum DebugLevel {
    ERROR = 0,
    WARN = 1,
    INFO = 2,
    DEBUG = 3,
    TRACE = 4
}

export const DEBUG_MODE = true;
export const CURRENT_DEBUG_LEVEL = DebugLevel.INFO; // Default level, can be changed

// Debug logging helper
export const debugLog = (message: string, data?: any, level: DebugLevel = DebugLevel.DEBUG): void => {
    if (!DEBUG_MODE || level > CURRENT_DEBUG_LEVEL) {
        return;
    }

    const logFn = level === DebugLevel.ERROR ? console.error :
                  level === DebugLevel.WARN ? console.warn :
                  level === DebugLevel.INFO ? console.info :
                  console.log;

    const prefix = `[${DebugLevel[level]}] `;
    if (data) {
        if (data instanceof Error) {
            // stringify does not work on Errors directly
            logFn(prefix + message, JSON.stringify(data, Object.getOwnPropertyNames(data), 2));
        } else {
            logFn(prefix + message, JSON.stringify(data, null, 2));
        }
    } else {
        logFn(prefix + message);
    }
};

// Helper functions to make logging more semantic
export const logError = (message: string, data?: any) => debugLog(message, data, DebugLevel.ERROR);
export const logWarn = (message: string, data?: any) => debugLog(message, data, DebugLevel.WARN);
export const logInfo = (message: string, data?: any) => debugLog(message, data, DebugLevel.INFO);
export const logDebug = (message: string, data?: any) => debugLog(message, data, DebugLevel.DEBUG);
export const logTrace = (message: string, data?: any) => debugLog(message, data, DebugLevel.TRACE);

export const logMutation = (mutation: MutationRecord): void => {
    if (!DEBUG_MODE) return;

    // Track attribute changes
    if (mutation.type === 'attributes') {
        const target = mutation.target as Element;
        const attributeName = mutation.attributeName;
        logTrace('Attribute changed:', {
            type: 'attribute_change',
            ...(attributeName && { attribute: attributeName }),
            element: target.tagName,
            classes: target.className,
            oldValue: mutation.oldValue,
            newValue: attributeName ? target.getAttribute(attributeName) : null,
            hasDataStatus: target.hasAttribute('data-status'),
            dataStatus: target.getAttribute('data-status'),
            hasDataTooltip: target.hasAttribute('data-tooltip'),
            dataTooltip: target.getAttribute('data-tooltip'),
            parentClasses: target.parentElement?.className,
            timestamp: new Date().toISOString(),
            stack: new Error().stack
        });
    }

    // Track element additions/removals
    const processNode = (node: Node, type: 'added' | 'removed') => {
        if (node.nodeType === Node.ELEMENT_NODE) {
            const el = node as Element;
            if (el.classList?.contains('occludable-update') ||
                el.hasAttribute('data-status') ||
                el.hasAttribute('data-tooltip')) {
                debugLog(`Element ${type}:`, {
                    type: `node_${type}`,
                    element: el.tagName,
                    classes: el.className,
                    hasDataStatus: el.hasAttribute('data-status'),
                    dataStatus: el.getAttribute('data-status'),
                    hasDataTooltip: el.hasAttribute('data-tooltip'),
                    dataTooltip: el.getAttribute('data-tooltip'),
                    parentClasses: el.parentElement?.className,
                    timestamp: new Date().toISOString(),
                    stack: new Error().stack
                });
            }
        }
    };

    // Process added nodes
    if (mutation.addedNodes.length > 0) {
        Array.from(mutation.addedNodes).forEach(node => processNode(node, 'added'));
    }

    // Process removed nodes
    if (mutation.removedNodes.length > 0) {
        Array.from(mutation.removedNodes).forEach(node => processNode(node, 'removed'));
    }
};

function isFirefox() {
    return navigator.userAgent.toLowerCase().indexOf('firefox') > -1;
}

export function setupAttributeDebugWrappers(): void {
    // Add a debug wrapper for setAttribute
    const originalSetAttribute = Element.prototype.setAttribute;
    Element.prototype.setAttribute = function (name, value) {
        debugLog('setAttribute called:', {
            type: 'set_attribute',
            name,
            value,
            element: this.tagName,
            classes: this.className,
            hasDataStatus: this.hasAttribute('data-status'),
            dataStatus: this.getAttribute('data-status'),
            hasDataTooltip: this.hasAttribute('data-tooltip'),
            dataTooltip: this.getAttribute('data-tooltip'),
            parentClasses: this.parentElement?.className,
            stack: new Error().stack
        });
        originalSetAttribute.call(this, name, value);
    };

    // Add a debug wrapper for removeAttribute
    const originalRemoveAttribute = Element.prototype.removeAttribute;
    Element.prototype.removeAttribute = function (name) {
        debugLog('removeAttribute called:', {
            type: 'remove_attribute',
            name,
            element: this.tagName,
            classes: this.className,
            hasDataStatus: this.hasAttribute('data-status'),
            dataStatus: this.getAttribute('data-status'),
            hasDataTooltip: this.hasAttribute('data-tooltip'),
            dataTooltip: this.getAttribute('data-tooltip'),
            parentClasses: this.parentElement?.className,
            stack: new Error().stack
        });
        originalRemoveAttribute.call(this, name);
    };
}

// restrictionUtils.ts
export function enforceMethodRestriction(
    className: string,
    allowedFiles: string[],
    constructorFiles: string[] | null = null
) {
    console.log(`WE ARE IN PROD MODE?: ${__PROD__}`)
    if (__PROD__) return;

    if (isFirefox()) {
        console.log("Not enforcing.")
        return;
    }

    const error = new Error();
    const stack = error.stack || '';

    const getCallerInfo = (stackLines: string[]) => {
        // Find the relevant stack frame (skip enforceMethodRestriction and constructor frames)
        let callerLine = '';
        let methodName = 'unknown';

        for (const line of stackLines) {
            // Skip the utility function itself
            if (line.includes('enforceMethodRestriction')) continue;

            // If we find a constructor call, mark it
            if (line.includes(`new ${className}`)) {
                methodName = 'constructor';
                callerLine = line;
                break;
            }

            // Look for method calls
            const methodMatch = line.match(new RegExp(`${className}\\.(\\w+)`));
            if (methodMatch && methodMatch[1]) {
                methodName = methodMatch[1];
                callerLine = line;
                break;
            }
        }

        // Extract filename from chrome-extension:// URL
        const fileMatch = callerLine.match(/\/(\w+-\w+)\.js/);
        const fileName = fileMatch?.[1] || 'unknown';

        return {
            method: methodName,
            file: fileName
        };
    };

    const stackLines = stack.split('\n');
    const callerInfo = getCallerInfo(stackLines);
    const isConstructor = callerInfo.method === 'constructor';

    const createErrorMessage = (type: 'constructor' | 'method', allowed: string[]) => {
        const violationType = type === 'constructor' ? 'instantiated' : 'called';
        return [
            `Class "${className}" ${type} violation:`,
            `${className}.${callerInfo.method} can only be ${violationType} from:`,
            ...allowed.map(f => `  - ${f}`),
            `Current call stack:`,
            `  - File: ${callerInfo.file}`,
            `  - Method: ${callerInfo.method}`,
            `\nFull stack trace:`,
            ...stackLines.slice(0, 5).map(line => `  ${line.trim()}`)
        ].join('\n');
    };

    if (isConstructor) {
        if (!constructorFiles) return;

        const isAllowedConstructor = constructorFiles.some(file => {
            const baseFile = file.replace(/\.(js|ts)$/, '');
            return callerInfo.file.includes(baseFile);
        });

        if (!isAllowedConstructor) {
            throw new Error(createErrorMessage('constructor', constructorFiles));
        }
        return;
    }

    const isAllowedMethod = allowedFiles.some(file => {
        const baseFile = file.replace(/\.(js|ts)$/, '');
        return callerInfo.file.includes(baseFile);
    });

    if (!isAllowedMethod) {
        throw new Error(createErrorMessage('method', allowedFiles));
    }
}