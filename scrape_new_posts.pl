#!/usr/bin/env perl
# scrape_new_posts.pl — Fetch new MND PLA activity posts, extract JSON, download images.
# Usage: perl scrape_new_posts.pl [START_ID] [END_ID]
# Refs: https://github.com/Agent-Mouses/mnd-pla-tracker/issues/3
use strict; use warnings;
use JSON::PP;
use File::Path qw(make_path);

my $START = $ARGV[0] || 86379;
my $END   = $ARGV[1] || 86503;
my $DATA  = "mnd_pla_data";
my $BASE  = "https://www.mnd.gov.tw";

my $json = JSON::PP->new->utf8->pretty->canonical;
my ($saved, $skipped, $img_ok, $img_fail) = (0, 0, 0, 0);

open my $idx_fh, ">>", "$DATA/download_index.csv" or die $!;
open my $jl_fh,  ">>", "$DATA/records.jsonl"       or die $!;

for my $id ($START..$END) {
    my $url = "$BASE/en/news/plaact/$id";
    my $html = `curl -sL "$url"`;
    my $final_url = `curl -sL -o /dev/null -w '%{url_effective}' "$url"`;
    chomp $final_url;

    # Skip redirects (not a real page)
    if ($final_url !~ /plaact\/$id/) {
        print "$id: redirect\n";
        print $idx_fh "$id,$url,$final_url,200,,,0,skipped_redirect\n";
        $skipped++;
        next;
    }

    # Skip non-PLA pages
    if ($html !~ /PLA/i || $html !~ /aircraft|sortie|ship|ADIZ|偵獲/i) {
        print "$id: no PLA content\n";
        print $idx_fh "$id,$url,$final_url,200,,,0,skipped_no_PLA_in_text\n";
        $skipped++;
        next;
    }

    # Save HTML
    make_path("$DATA/html");
    open my $hf, ">", "$DATA/html/$id.html" or die $!;
    print $hf $html;
    close $hf;

    # Extract fields
    my %rec = (id => $id+0, requested_url => $url, final_url => $final_url);

    # Page title
    ($rec{page_title}) = $html =~ /<h1 class="title">(.*?)<\/h1>/s;
    $rec{page_title} //= "";

    # Issue date
    ($rec{issue_date}) = $html =~ /(\d{4}\.\d{2}\.\d{2})/;

    # Issuing authority
    ($rec{issuing_authority}) = $html =~ /Issuing Authority[：:]\s*(.*?)<\/span>/;

    # Full text (strip tags)
    my $ft = $html;
    $ft =~ s/<[^>]+>/ /g;
    $ft =~ s/\s+/ /g;
    $ft =~ s/^\s+|\s+$//g;
    $rec{full_text} = $ft;

    # Report window: "6 a.m. ... (UTC+8)"
    ($rec{report_window}) = $ft =~ /(6 a\.m\.\s+\w+\.?\s+\d+\s+\([^)]+\)\s+to\s+6 a\.m\.\s+\w+\.?\s+\d+\s+\([^)]+\)\s+\(UTC\+8\))/;
    $rec{report_window} //= "";

    # PLA activities text
    ($rec{pla_activities_text}) = $ft =~ /PLA activities[：:]\s*(.*?)(?:ROC Armed Forces|Keywords|Share)/s;
    $rec{pla_activities_text} //= "";
    $rec{pla_activities_text} =~ s/^\s+|\s+$//g;

    # Total aircraft
    my ($total) = $rec{pla_activities_text} =~ /(\d+)\s+sorties?\s+of\s+PLA\s+aircraft/i;
    $rec{total_aircraft} = ($total || 0) + 0;

    # UAV flag
    $rec{uav_keyword_flag} = ($ft =~ /UAV|UAS|drone|無人機/i) ? JSON::PP::true : JSON::PP::false;

    # Old-format fields
    $rec{older_page_date} = undef;
    $rec{aircraft_type} = undef;
    $rec{activity_area} = undef;
    $rec{reactions} = undef;

    # --- Download images ---
    my @media;
    # NewUpload images (modern format)
    while ($html =~ /src="(https?:\/\/www\.mnd\.gov\.tw\/NewUpload\/[^"]+)"/g) {
        my $img_url = $1;
        my ($fname) = $img_url =~ /\/([^\/]+)$/;
        my $dest_dir = "$DATA/target_media/$id";
        make_path($dest_dir);
        my $seq = sprintf("%03d", scalar(@media) + 1);
        my $dest = "$dest_dir/${seq}_${fname}";

        my $rc = system("curl", "-sS", "-o", $dest, $img_url);
        my $size = -s $dest || 0;
        if ($rc == 0 && $size > 0) {
            push @media, {
                kind => "newupload_img",
                selection_rule => "newupload_filename_match",
                source_url => $img_url,
                label => $fname,
                status_code => 200+0,
                content_type => ($fname =~ /\.jpg/i ? "image/jpeg" : "image/png"),
                saved_path => $dest,
                size_bytes => $size+0,
            };
            $img_ok++;
        } else {
            $img_fail++;
            unlink $dest if -f $dest;
        }
    }

    # File/ links (older format)
    while ($html =~ /href="\.\.\/File\/(\d+)"/g) {
        my $fid = $1;
        my $furl = "$BASE/File/$fid";
        my $dest_dir = "$DATA/target_media/$id";
        make_path($dest_dir);
        my $tmp = "$dest_dir/_tmp_$fid";

        my $headers = `curl -sS -D - -o "$tmp" "$furl" 2>&1`;
        my $size = -s $tmp || 0;
        if ($size > 0) {
            my $fname;
            if ($headers =~ /filename\*=UTF-8''(.+?)[\r\n]/) {
                $fname = $1;
                $fname =~ s/%([0-9A-Fa-f]{2})/chr(hex($1))/ge;
            } elsif ($headers =~ /filename="(.+?)"/) {
                $fname = $1;
            } else {
                $fname = "$fid.bin";
            }
            $fname =~ s/[\/\\:*?"<>|]/_/g;
            rename $tmp, "$dest_dir/$fname";
            push @media, {
                kind => "file_download",
                source_url => $furl,
                label => $fname,
                saved_path => "$dest_dir/$fname",
                size_bytes => $size+0,
            };
            $img_ok++;
        } else {
            $img_fail++;
            unlink $tmp if -f $tmp;
        }
        select(undef, undef, undef, 0.3);
    }

    $rec{target_media_count} = scalar(@media) + 0;
    $rec{target_media_files} = \@media;

    # Save JSON
    make_path("$DATA/json");
    open my $jf, ">", "$DATA/json/$id.json" or die $!;
    print $jf $json->encode(\%rec);
    close $jf;

    # Append to JSONL
    my $oneline = JSON::PP->new->utf8->canonical->encode(\%rec);
    print $jl_fh "$oneline\n";

    # Append to download_index
    my $note = @media ? "saved" : "saved_no_media";
    print $idx_fh "$id,$url,$final_url,200,$DATA/html/$id.html,$DATA/json/$id.json," . scalar(@media) . ",$note\n";

    $saved++;
    my $media_str = @media ? " [" . scalar(@media) . " media]" : "";
    print "$id: saved | $rec{total_aircraft} aircraft$media_str\n";
    select(undef, undef, undef, 0.5);
}

close $idx_fh;
close $jl_fh;

print "\n=== Summary ===\n";
print "Scanned: " . ($END - $START + 1) . " IDs ($START-$END)\n";
print "Saved: $saved | Skipped: $skipped\n";
print "Images: $img_ok downloaded, $img_fail failed\n";
