package main

import (
	"fmt"
	runewidth "github.com/mattn/go-runewidth"
)

func main() {
	str := "สวัสดี"
	for i, r := range []rune(str) {
		fmt.Printf("Rune %d: %q (U+%04X) -> Width = %d\n", i, r, r, runewidth.RuneWidth(r))
	}
}
