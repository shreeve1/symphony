"use client";

import {
	type RefObject,
	useEffect,
	useLayoutEffect,
	useRef,
	useState,
} from "react";

export type SlashPickerValue = { value: string; label?: string };
export type SlashPickerField = {
	id: string;
	title: string;
	values: readonly SlashPickerValue[];
	onSelect: (value: string) => void;
	allowFreeText?: boolean;
};

type Command =
	| { start: number; level: "field" }
	| { start: number; level: "value"; fieldId: string; valueStart: number };

function triggerAt(value: string, caret: number): Command | null {
	const match = /(?:^|\s)(\/[^\s]*)$/.exec(value.slice(0, caret));
	if (!match) return null;
	return { start: caret - match[1].length, level: "field" };
}

export function SlashPickerTextarea({
	value,
	onChange,
	fields,
	testid,
	rows = 4,
	className,
	autoFocus = false,
	disabled = false,
	placeholder,
	textareaRef: externalTextareaRef,
}: {
	value: string;
	onChange: (value: string) => void;
	fields: readonly SlashPickerField[];
	testid: string;
	rows?: number;
	className?: string;
	autoFocus?: boolean;
	disabled?: boolean;
	placeholder?: string;
	textareaRef?: RefObject<HTMLTextAreaElement | null>;
}) {
	const internalTextareaRef = useRef<HTMLTextAreaElement | null>(null);
	const textareaRef = externalTextareaRef ?? internalTextareaRef;
	const listRef = useRef<HTMLDivElement | null>(null);
	const pendingCaretRef = useRef<number | null>(null);
	const [command, setCommand] = useState<Command | null>(null);
	const [caret, setCaret] = useState(0);
	const [activeIndex, setActiveIndex] = useState(0);
	const listId = `${testid}-slash-listbox`;
	const field =
		command?.level === "value"
			? fields.find((candidate) => candidate.id === command.fieldId)
			: undefined;
	const query = command
		? value
				.slice(
					command.level === "field" ? command.start + 1 : command.valueStart,
					caret,
				)
				.trim()
				.toLowerCase()
		: "";
	const fieldEntries = fields.filter((candidate) =>
		candidate.title.toLowerCase().includes(query),
	);
	const valueEntries = (() => {
		if (!field || command?.level !== "value") return [];
		const filtered = field.values.filter((candidate) => {
			if (!query) return true;
			if (!candidate.value) return false;
			const label = candidate.label ?? candidate.value;
			return (
				label.toLowerCase().includes(query) ||
				candidate.value.toLowerCase().includes(query)
			);
		});
		if (!field.allowFreeText || !query) return filtered;
		const typed = value.slice(command.valueStart, caret).trim();
		const exact = field.values.some((candidate) => {
			const label = candidate.label ?? candidate.value;
			return (
				candidate.value.toLowerCase() === query || label.toLowerCase() === query
			);
		});
		return exact ? filtered : [...filtered, { value: typed, label: typed }];
	})();
	const entries = command?.level === "value" ? valueEntries : fieldEntries;
	const open = command !== null;
	const listName = field ? `${field.title} values` : "Issue fields";

	useEffect(
		() => setActiveIndex(0),
		[query, command?.level, command?.level === "value" ? command.fieldId : ""],
	);

	useEffect(() => {
		if (!open) return;
		listRef.current
			?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`)
			?.scrollIntoView({ block: "nearest" });
	}, [activeIndex, open]);

	useLayoutEffect(() => {
		const position = pendingCaretRef.current;
		if (position === null) return;
		textareaRef.current?.focus();
		textareaRef.current?.setSelectionRange(position, position);
		pendingCaretRef.current = null;
	}, [value]);

	const restoreCaret = (position: number) => {
		pendingCaretRef.current = position;
	};

	const selectField = (next: SlashPickerField) => {
		if (!command) return;
		const replacement = `/${next.title} `;
		const nextCaret = command.start + replacement.length;
		onChange(value.slice(0, command.start) + replacement + value.slice(caret));
		setCaret(nextCaret);
		setCommand({
			start: command.start,
			level: "value",
			fieldId: next.id,
			valueStart: nextCaret,
		});
		restoreCaret(nextCaret);
	};

	const selectValue = (next: SlashPickerValue) => {
		if (!command || !field) return;
		field.onSelect(next.value);
		onChange(value.slice(0, command.start) + value.slice(caret));
		setCaret(command.start);
		setCommand(null);
		restoreCaret(command.start);
	};

	const commitActive = () => {
		const active = entries[activeIndex];
		if (!active) return false;
		if (command?.level === "value") selectValue(active as SlashPickerValue);
		else selectField(active as SlashPickerField);
		return true;
	};

	return (
		<div className="relative">
			<textarea
				ref={textareaRef}
				data-testid={testid}
				value={value}
				rows={rows}
				autoFocus={autoFocus}
				disabled={disabled}
				placeholder={placeholder}
				role="combobox"
				aria-autocomplete="list"
				aria-expanded={open}
				aria-controls={open ? listId : undefined}
				aria-activedescendant={
					open && entries[activeIndex]
						? `${listId}-option-${activeIndex}`
						: undefined
				}
				onChange={(event) => {
					const next = event.target.value;
					const nextCaret = event.target.selectionStart;
					onChange(next);
					setCaret(nextCaret);
					if (
						command?.level === "value" &&
						field &&
						nextCaret >= command.valueStart &&
						next.slice(command.start, command.valueStart) === `/${field.title} `
					) {
						return;
					}
					setCommand(triggerAt(next, nextCaret));
				}}
				onSelect={(event) => setCaret(event.currentTarget.selectionStart)}
				onBlur={() => setCommand(null)}
				onKeyDown={(event) => {
					if (!open) return;
					if (event.key === "ArrowDown" || event.key === "ArrowUp") {
						event.preventDefault();
						const delta = event.key === "ArrowDown" ? 1 : -1;
						setActiveIndex((index) =>
							Math.max(0, Math.min(index + delta, entries.length - 1)),
						);
					} else if (event.key === "Tab" || event.key === "Enter") {
						if (commitActive()) event.preventDefault();
					} else if (event.key === "Escape") {
						event.preventDefault();
						event.stopPropagation();
						setCommand(null);
					}
				}}
				className={className}
			/>
			{open && (
				<div
					ref={listRef}
					id={listId}
					role="listbox"
					aria-label={listName}
					className="absolute z-50 mt-1 max-h-44 w-full overflow-auto rounded-md border bg-background p-1 shadow-lg"
				>
					{entries.map((entry, index) => {
						const label =
							"title" in entry ? entry.title : (entry.label ?? entry.value);
						return (
							<button
								type="button"
								key={"id" in entry ? entry.id : `${entry.value}-${index}`}
								id={`${listId}-option-${index}`}
								data-index={index}
								role="option"
								aria-selected={index === activeIndex}
								onMouseEnter={() => setActiveIndex(index)}
								onMouseDown={(event) => event.preventDefault()}
								onClick={() => {
									if (command?.level === "value")
										selectValue(entry as SlashPickerValue);
									else selectField(entry as SlashPickerField);
								}}
								className={`block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-muted ${index === activeIndex ? "bg-muted" : ""}`}
							>
								{label}
							</button>
						);
					})}
					{entries.length === 0 && (
						<div className="px-2 py-1.5 text-sm text-muted-foreground">
							No matches
						</div>
					)}
				</div>
			)}
		</div>
	);
}
