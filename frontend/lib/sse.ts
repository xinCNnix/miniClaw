/**
 * SSE (Server-Sent Events) parser and handler
 */

export interface SSEMessage {
  data: string;
  event?: string;
  id?: string;
  retry?: number;
}

export interface ParsedSSEEvent {
  type: 'thinking_start' | 'tool_call' | 'content_delta' | 'tool_output' | 'error' | 'done' | 'self_correction';
  content?: string;
  tool_calls?: any[];
  error?: string;
  tool_name?: string;
  output?: any;
  status?: string;
  session_id?: string;
}

/**
 * Parse SSE message text
 */
export function parseSSEMessage(line: string): SSEMessage | null {
  // Empty line
  if (!line.trim()) return null;

  // Comment line
  if (line.trim().startsWith(':')) return null;

  const message: SSEMessage = {
    data: '',
  };

  // SSE format allows multiple lines, each with "field: value"
  // Split by newline and process each line
  const lines = line.split('\n');

  for (const singleLine of lines) {
    if (!singleLine.trim()) continue;
    if (singleLine.trim().startsWith(':')) continue;

    // Split by first colon to get field and value
    const colonIndex = singleLine.indexOf(':');

    if (colonIndex === -1) {
      // No colon, treat entire line as data
      message.data = singleLine;
    } else {
      const field = singleLine.slice(0, colonIndex).trim();
      let value = singleLine.slice(colonIndex + 1);

      // Remove leading space from value (SSE spec)
      if (value.startsWith(' ')) {
        value = value.slice(1);
      }

      if (field === 'data') {
        // Append data (SSE allows multiple data lines)
        message.data += value;
      } else if (field === 'event') {
        message.event = value;
      } else if (field === 'id') {
        message.id = value;
      } else if (field === 'retry') {
        message.retry = parseInt(value, 10);
      }
    }
  }

  return message;
}

/**
 * Parse SSE event and convert to our event format
 */
export function parseSSEEvent(message: SSEMessage): ParsedSSEEvent | null {
  try {
    const data = JSON.parse(message.data);
    return data as ParsedSSEEvent;
  } catch {
    return null;
  }
}

/**
 * Connect to SSE stream and process events
 */
export async function* connectSSEStream(
  url: string,
  request: object,
  options?: {
    signal?: AbortSignal;
    onMessage?: (event: ParsedSSEEvent) => void;
    onError?: (error: Error) => void;
    onClose?: () => void;
  }
): AsyncGenerator<ParsedSSEEvent, void, void> {
  const { signal } = options || {};

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal,
    });

    if (!response.ok) {
      throw new Error(`SSE request failed: ${response.statusText}`);
    }

    if (!response.body) {
      throw new Error('Response body is null');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        options?.onClose?.();
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep incomplete line in buffer

      for (const line of lines) {
        const sseMessage = parseSSEMessage(line);

        if (sseMessage && sseMessage.data) {
          const event = parseSSEEvent(sseMessage);

          if (event) {
            options?.onMessage?.(event);
            yield event;

            // Stop if done
            if (event.type === 'done') {
                return;
            }
          }
        }
      }
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      // Normal abort
      return;
    }

    options?.onError?.(error as Error);
    throw error;
  }
}

/**
 * Format SSE event for sending
 */
export function formatSSEEvent(event: ParsedSSEEvent): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}
