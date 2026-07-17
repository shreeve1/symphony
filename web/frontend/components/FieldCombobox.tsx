"use client";

import { useEffect, useRef, useState } from "react";

export type ComboOption = { value: string; label?: string };

function labelFor(
	options: readonly ComboOption[],
	value: string,
): string {
	return options.find((option) => option.value === value)?.label ?? value;
}

// Searchable zero-dependency combobox. Free-text mode updates the submitted
// value as the operator types; selection-only mode only submits clicked options.
// Extracted from NewIssueModal.tsx so the automations form can use the same
// client primitive for skill / agent / model inputs (issue #459 parity).
export function FieldCombobox({
	label,
	testid,
	value,
	onChange,
	options,
	emptyHint,
	allowFreeText = false,
}: {
	label: string;
	testid: string;
	value: string;
	onChange: (value: string) => void;
	options: readonly ComboOption[];
	emptyHint?: string;
	allowFreeText?: boolean;
}) {
	const [open, setOpen] = useState(false);
	const [draft, setDraft] = useState(labelFor(options, value));
	const [activeIndex, setActiveIndex] = useState(-1);
	const listRef = useRef<HTMLDivElement | null>(null);
	const listId = `${testid}-listbox`;
	const normalizedDraft = draft.trim().toLowerCase();
	// A draft that still mirrors the selected value (e.g. the preselected
	// default model) is not a search: show the full list until the operator
	// actually types.
	const filterActive =
		normalizedDraft !== labelFor(options, value).trim().toLowerCase();
	const filtered = options.filter((option) => {
		const optionLabel = option.label ?? option.value;
		return (
			!filterActive ||
			!normalizedDraft ||
			optionLabel.toLowerCase().includes(normalizedDraft) ||
			option.value.toLowerCase().includes(normalizedDraft)
		);
	});

	const emptyLabel = emptyHint ? `— (${emptyHint})` : "—";
	const entries: ComboOption[] = [
		{ value: "", label: emptyLabel },
		...filtered,
	];

	useEffect(() => {
		setDraft(labelFor(options, value));
	}, [options, value]);

	useEffect(() => {
		setActiveIndex(-1);
	}, [open, normalizedDraft]);

	useEffect(() => {
		if (!open || activeIndex < 0) return;
		listRef.current
			?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`)
			?.scrollIntoView({ block: "nearest" });
	}, [open, activeIndex]);

	const choose = (next: string) => {
		onChange(next);
		setDraft(labelFor(options, next));
		setOpen(false);
		setActiveIndex(-1);
	};

	const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
		if (e.key === "ArrowDown") {
			e.preventDefault();
			if (!open) setOpen(true);
			else setActiveIndex((i) => Math.min(i + 1, entries.length - 1));
		} else if (e.key === "ArrowUp") {
			e.preventDefault();
			if (!open) setOpen(true);
			else setActiveIndex((i) => Math.max(i - 1, 0));
		} else if (e.key === "Enter") {
			if (open && activeIndex >= 0 && activeIndex < entries.length) {
				e.preventDefault();
				choose(entries[activeIndex].value);
			}
		} else if (e.key === "Escape" && open) {
			// Close only the popup; never let an outside Escape-on-close
			// handler treat this as the modal's intent.
			e.preventDefault();
			e.stopPropagation();
			setOpen(false);
			setActiveIndex(-1);
			if (!allowFreeText) setDraft(labelFor(options, value));
		}
	};

	return (
		<label className="relative block flex-1 space-y-1">
			<span className="text-xs font-medium text-muted-foreground">{label}</span>
			<input
				data-testid={testid}
				role="combobox"
				aria-expanded={open}
				aria-controls={listId}
				aria-autocomplete="list"
				aria-activedescendant={
					open && activeIndex >= 0
						? `${testid}-option-${activeIndex}`
						: undefined
				}
				value={draft}
				placeholder={emptyLabel}
				onFocus={() => setOpen(true)}
				onKeyDown={onKeyDown}
				onChange={(e) => {
					setDraft(e.target.value);
					setOpen(true);
					if (allowFreeText) onChange(e.target.value);
					if (!allowFreeText && e.target.value === "") onChange("");
				}}
				onBlur={() => {
					setOpen(false);
					if (!allowFreeText) setDraft(labelFor(options, value));
				}}
				className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:border-foreground/40"
			/>
			{open && (
				<div
					ref={listRef}
					id={listId}
					role="listbox"
					className="absolute z-50 mt-1 max-h-44 w-full overflow-auto rounded-md border bg-background p-1 shadow-lg"
				>
					{entries.map((option, index) => {
						const active = index === activeIndex;
						const isEmpty = option.value === "";
						return (
							<button
								type="button"
								key={option.value || "__empty__"}
								id={`${testid}-option-${index}`}
								data-index={index}
								data-testid={`${testid}-option`}
								role="option"
								aria-selected={active}
								onMouseEnter={() => setActiveIndex(index)}
								onMouseDown={(e) => e.preventDefault()}
								onClick={() => choose(option.value)}
								className={`block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-muted ${
									isEmpty ? "text-muted-foreground" : ""
								} ${active ? "bg-muted" : ""}`}
							>
								{option.label ?? option.value}
							</button>
						);
					})}
					{filtered.length === 0 && (
						<div className="px-2 py-1.5 text-sm text-muted-foreground">
							No matches
						</div>
					)}
				</div>
			)}
		</label>
	);
}
