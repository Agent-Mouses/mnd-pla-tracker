#!/usr/bin/env perl
# rebuild_db.pl — Parse all records.jsonl, produce activities CSV + SQLite SQL.
# Replicates text_parser.py logic in Perl. Run on host with:
#   perl rebuild_db.pl              # generates output/ CSVs + rebuild.sql
#   sqlite3 tracker.db < rebuild.sql  # apply to SQLite
use strict; use warnings;
use JSON::PP;
use File::Path qw(make_path);
use Encode qw(encode_utf8);

my $DATA = "mnd_pla_data";
my $OUT  = "output";
make_path($OUT);

my %AIRCRAFT = (
    'J-10'=>'fighter','J-11'=>'fighter','J-16'=>'fighter','J-7'=>'fighter',
    'Su-30'=>'fighter','Su-35'=>'fighter','JH-7'=>'fighter',
    'H-6'=>'bomber',
    'UAV'=>'UAV','UAS'=>'UAV','TB-001'=>'UAV','BZK'=>'UAV','WZ-7'=>'UAV',
    'CH-4'=>'UAV','CH-5'=>'UAV',
    'Y-8'=>'ISR','Y-9'=>'ISR','KJ-'=>'AEW','KJ500'=>'AEW','KJ200'=>'AEW',
    'RECCE'=>'ISR','ASW'=>'ASW','EW'=>'EW','ELINT'=>'ELINT',
    'Y-20'=>'transport','IL-76'=>'transport',
    'helicopter'=>'helicopter','tanker'=>'tanker',
);

my @AREAS = (
    [qr/southwest(?:ern)?/i, 'SW_ADIZ'], [qr/southeast(?:ern)?/i, 'SE_ADIZ'],
    [qr/north(?:ern)?/i, 'N_ADIZ'], [qr/east(?:ern)?/i, 'E_ADIZ'],
    [qr/median\s*line/i, 'median_line'], [qr/Taiwan\s*Strait/i, 'strait'],
);

my %MONTHS = (jan=>1,feb=>2,mar=>3,apr=>4,may=>5,jun=>6,jul=>7,aug=>8,sep=>9,oct=>10,nov=>11,dec=>12);

sub parse_date {
    my ($rec) = @_;
    my $ft = $rec->{full_text} || '';
    if ($ft =~ /PLA Activities\s+(\d{4})\.(\d{1,2})\.(\d{1,2})/) {
        return sprintf("%04d-%02d-%02d", $1, $2, $3);
    }
    my $opd = $rec->{older_page_date} || '';
    if ($opd =~ /(\w{3,9})\.?\s*(\d{1,2}),?\s*(\d{4})/) {
        my $m = $MONTHS{lc(substr($1,0,3))} || 0;
        return sprintf("%04d-%02d-%02d", $3, $m, $2) if $m;
    }
    return '';
}

sub classify_aircraft {
    my ($text) = @_;
    my %seen; my @types;
    for my $k (keys %AIRCRAFT) {
        if (index(lc($text), lc($k)) >= 0 && !$seen{$AIRCRAFT{$k}}++) {
            push @types, $AIRCRAFT{$k};
        }
    }
    return \@types;
}

sub extract_areas {
    my ($text) = @_;
    my %seen; my @areas;
    for my $a (@AREAS) {
        if ($text =~ $a->[0] && !$seen{$a->[1]}++) {
            push @areas, $a->[1];
        }
    }
    return \@areas;
}

sub extract_total {
    my ($text) = @_;
    return $1+0 if $text =~ /(\d+)\s+sorties?\s+of\s+PLA\s+aircraft/i;
    return $1+0 if $text =~ /(\d+)\s+PLA\s+aircraft/i;
    return 0;
}

sub extract_crossed {
    my ($text) = @_;
    return $1+0 if $text =~ /(\d+)\s+out\s+of\s+\d+\s+sorties?\s+crossed/i;
    return $1+0 if $text =~ /(\d+)\s+(?:sorties?\s+)?crossed\s+the\s+median/i;
    return 0;
}

sub extract_ships {
    my ($text) = @_;
    my $t = 0;
    $t += $1 if $text =~ /(\d+)\s+PLAN\s+(?:ships?|vessels?)/i;
    $t += $1 if $text =~ /(\d+)\s+official\s+ships?/i;
    return $t;
}

sub extract_entered {
    my ($text) = @_;
    return $1+0 if $text =~ /(\d+)\s+(?:out\s+of\s+\d+\s+sorties?\s+)?(?:entered|crossed.*?entered)\s+Taiwan/i;
    return 0;
}

sub csv_escape {
    my ($v) = @_;
    $v //= '';
    $v =~ s/"/""/g;
    return qq{"$v"} if $v =~ /[,"\n\r]/;
    return $v;
}

# --- Main ---
open my $fh, '<', "$DATA/records.jsonl" or die "Cannot open records.jsonl: $!";
open my $csv, '>:raw', "$OUT/mnd_pla_activities.csv" or die $!;
open my $sql, '>:raw', "$OUT/rebuild.sql" or die $!;

print $csv "id,date,total_aircraft,aircraft_types,has_uav,crossed_median,entered_adiz,ships,areas,source,url,page_title,report_window,pla_activities_text\n";

print $sql "DROP TABLE IF EXISTS activities;\n";
print $sql "DROP TABLE IF EXISTS sorties;\n";
print $sql <<'SQL';
CREATE TABLE activities (
    id INTEGER PRIMARY KEY, date TEXT, total_aircraft INTEGER,
    aircraft_types TEXT, has_uav INTEGER DEFAULT 0,
    crossed_median INTEGER DEFAULT 0, entered_adiz INTEGER DEFAULT 0,
    ships INTEGER DEFAULT 0, areas TEXT, source TEXT,
    url TEXT, page_title TEXT, report_window TEXT,
    aircraft_type_raw TEXT, pla_activities_text TEXT,
    has_image INTEGER DEFAULT 0, ocr_date TEXT,
    ocr_total_sorties INTEGER, ocr_has_uav INTEGER, ocr_zones_json TEXT
);
CREATE TABLE sorties (
    id INTEGER PRIMARY KEY, record_id INTEGER, zone TEXT,
    time_window TEXT, aircraft_types TEXT, total_sorties INTEGER,
    crossed_median INTEGER, has_uav INTEGER
);
CREATE INDEX idx_act_date ON activities(date);
CREATE INDEX idx_act_uav ON activities(has_uav);
SQL

my ($total, $with_date, $with_uav, $with_media) = (0, 0, 0, 0);
my %by_source;

while (my $line = <$fh>) {
    chomp $line;
    next unless $line;
    my $rec = decode_json($line);
    my $id = $rec->{id};

    my $date = parse_date($rec);
    my $at = $rec->{aircraft_type} || '';
    my $pla = $rec->{pla_activities_text} || '';
    my $ft = $rec->{full_text} || '';
    my $all = "$at $pla $ft";

    my $types = classify_aircraft($all);
    my $has_uav = (grep { $_ eq 'UAV' } @$types) ? 1 : 0;
    $has_uav = 1 if $rec->{uav_keyword_flag};
    my $total_ac = $rec->{total_aircraft} || extract_total($all);
    my $crossed = extract_crossed($all);
    my $entered = extract_entered($all);
    my $ships = extract_ships($all);
    my $areas = extract_areas("$all " . ($rec->{page_title}||''));
    my $has_media = ($rec->{target_media_count}||0) > 0 ? 1 : 0;
    my $source = $has_media ? 'image' : ($at ? 'aircraft_type' : ($pla ? 'pla_text' : 'full_text'));

    my $types_str = join('+', @$types);
    my $areas_str = join('+', @$areas);

    # CSV
    print $csv join(',', $id, csv_escape($date), $total_ac, csv_escape($types_str),
        $has_uav, $crossed, $entered, $ships, csv_escape($areas_str), $source,
        csv_escape($rec->{final_url}||''), csv_escape($rec->{page_title}||''),
        csv_escape($rec->{report_window}||''), csv_escape($pla)), "\n";

    # SQL
    my $sq = sub { my $v = shift // ''; $v =~ s/'/''/g; return "'$v'" };
    print $sql "INSERT INTO activities (id,date,total_aircraft,aircraft_types,has_uav,crossed_median,entered_adiz,ships,areas,source,url,page_title,report_window,aircraft_type_raw,pla_activities_text,has_image) VALUES ($id,"
        . $sq->($date) . ",$total_ac," . $sq->($types_str) . ",$has_uav,$crossed,$entered,$ships,"
        . $sq->($areas_str) . "," . $sq->($source) . "," . $sq->($rec->{final_url}||'') . ","
        . $sq->($rec->{page_title}||'') . "," . $sq->($rec->{report_window}||'') . ","
        . $sq->($at) . "," . $sq->($pla) . ",$has_media);\n";

    $total++;
    $with_date++ if $date;
    $with_uav++ if $has_uav;
    $with_media++ if $has_media;
    $by_source{$source}++;
}

close $fh; close $csv; close $sql;

print "\n=== Database Rebuild Complete ===\n";
print "Total records:  $total\n";
print "With date:      $with_date\n";
print "With UAV:       $with_uav\n";
print "With media:     $with_media\n";
print "By source:\n";
for (sort keys %by_source) { print "  $_: $by_source{$_}\n" }
print "\nOutput:\n";
print "  $OUT/mnd_pla_activities.csv\n";
print "  $OUT/rebuild.sql\n";
print "\nTo apply to SQLite: sqlite3 tracker.db < $OUT/rebuild.sql\n";
