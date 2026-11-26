// The developer account receives private fields encrypted. Show these placeholders instead of ciphertext.

/** Placeholder for a hidden name, note or other text. */
export const MASKED_TEXT = 'ข้อมูลเข้ารหัส';

/** Placeholder for a hidden amount or price. */
export const MASKED_NUMBER = '••••••';

/**
 * Amounts arrive either as a plain value or as { value, is_masked }.
 * parent is the record the amount belongs to; its is_masked applies when the amount has none.
 */
export function readAmount(amount, parent) {
  if (amount && typeof amount === 'object' && 'value' in amount) {
    return { value: amount.value ?? null, isMasked: Boolean(amount.is_masked ?? parent?.is_masked) };
  }
  return { value: amount ?? null, isMasked: Boolean(parent?.is_masked) };
}

/** A text field of a record, or the placeholder when the record is masked. */
export const maskedField = (record, field, placeholder = MASKED_TEXT) => (record?.is_masked ? placeholder : record?.[field]);
